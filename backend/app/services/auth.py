from datetime import datetime, timedelta
from secrets import token_urlsafe
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import OAuthState, OAuthToken, User, UserPreference

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

GMAIL_SEND_SCOPES = {
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://mail.google.com/",
}


def ensure_oauth_config():
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=500,
            detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )


def create_oauth_state(db: Session) -> str:
    state = token_urlsafe(32)
    row = OAuthState(state=state, expires_at=datetime.utcnow() + timedelta(minutes=10))
    db.add(row)
    db.commit()
    return state


def build_google_auth_url(state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def validate_state(db: Session, state: str):
    row = db.query(OAuthState).filter(OAuthState.state == state).first()
    if not row:
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")
    if row.expires_at < datetime.utcnow():
        db.delete(row)
        db.commit()
        raise HTTPException(status_code=400, detail="Expired OAuth state.")
    db.delete(row)
    db.commit()


async def exchange_code_for_tokens(code: str) -> dict:
    payload = {
        "code": code,
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(
            GOOGLE_TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if res.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {res.text}")
    return res.json()


async def fetch_google_userinfo(access_token: str) -> dict:
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if res.status_code != 200:
        raise HTTPException(status_code=400, detail=f"User info fetch failed: {res.text}")
    return res.json()


def upsert_user_and_token(db: Session, userinfo: dict, token_payload: dict) -> User:
    email = (userinfo.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Google user email not found.")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email)
        db.add(user)
        db.flush()

    pref = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    if not pref:
        db.add(UserPreference(user_id=user.id))

    expires_in = int(token_payload.get("expires_in", 3600))
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    row = db.query(OAuthToken).filter(OAuthToken.user_id == user.id).first()
    if not row:
        row = OAuthToken(
            user_id=user.id,
            access_token=token_payload.get("access_token", ""),
            refresh_token=token_payload.get("refresh_token", ""),
            token_type=token_payload.get("token_type", "Bearer"),
            scope=token_payload.get("scope", ""),
            expires_at=expires_at,
            updated_at=datetime.utcnow(),
        )
        db.add(row)
    else:
        row.access_token = token_payload.get("access_token", row.access_token)
        row.refresh_token = token_payload.get("refresh_token", row.refresh_token)
        row.token_type = token_payload.get("token_type", row.token_type)
        row.scope = token_payload.get("scope", row.scope)
        row.expires_at = expires_at
        row.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(user)
    return user


def refresh_access_token(db: Session, row: OAuthToken) -> OAuthToken:
    if not row.refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token is missing. Reconnect Gmail.")

    payload = {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "refresh_token": row.refresh_token,
        "grant_type": "refresh_token",
    }
    with httpx.Client(timeout=20) as client:
        res = client.post(
            GOOGLE_TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if res.status_code != 200:
        raise HTTPException(status_code=401, detail=f"Token refresh failed: {res.text}")

    data = res.json()
    expires_in = int(data.get("expires_in", 3600))
    row.access_token = data.get("access_token", row.access_token)
    row.token_type = data.get("token_type", row.token_type)
    row.scope = data.get("scope", row.scope)
    row.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def get_valid_access_token(db: Session, user: User) -> str:
    row = db.query(OAuthToken).filter(OAuthToken.user_id == user.id).first()
    if not row:
        raise HTTPException(status_code=401, detail="Gmail is not connected.")

    if row.expires_at <= datetime.utcnow() + timedelta(minutes=2):
        row = refresh_access_token(db, row)
    return row.access_token


def has_gmail_send_scope(scope_value: str) -> bool:
    scopes = {scope.strip() for scope in scope_value.split() if scope.strip()}
    return bool(scopes & GMAIL_SEND_SCOPES)
