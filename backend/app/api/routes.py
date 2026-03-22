from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models import Email, InteractionEvent, OAuthToken, User, UserPreference
from app.schemas import (
    AuthConfigResponse,
    AuthStartResponse,
    AuthStatusResponse,
    EmailDetail,
    EventRequest,
    FeedbackRequest,
    InboxResponse,
    MessageResponse,
    SyncRequest,
    ViewMode,
)
from app.services.adaptation import rescore_user_emails
from app.services.gmail_sync import sync_gmail_inbox
from app.services.sync import ensure_demo_user, seed_mock_emails
from app.services.auth import (
    build_google_auth_url,
    create_oauth_state,
    ensure_oauth_config,
    exchange_code_for_tokens,
    fetch_google_userinfo,
    upsert_user_and_token,
    validate_state,
)

router = APIRouter()


def get_current_user(
    db: Session = Depends(get_db), x_user_email: Optional[str] = Header(default=None)
):
    if not x_user_email:
        return ensure_demo_user(db)

    email = x_user_email.strip().lower()
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user

    user = User(email=email)
    db.add(user)
    db.flush()
    db.add(UserPreference(user_id=user.id))
    db.commit()
    db.refresh(user)
    return user


@router.get("/auth/google/start", response_model=AuthStartResponse)
def auth_google_start(db: Session = Depends(get_db)):
    ensure_oauth_config()
    state = create_oauth_state(db)
    auth_url = build_google_auth_url(state)
    return AuthStartResponse(auth_url=auth_url)


@router.get("/auth/google/callback")
async def auth_google_callback(
    code: str = Query(...), state: str = Query(...), db: Session = Depends(get_db)
):
    ensure_oauth_config()
    validate_state(db, state)
    token_payload = await exchange_code_for_tokens(code)
    userinfo = await fetch_google_userinfo(token_payload.get("access_token", ""))
    user = upsert_user_and_token(db, userinfo, token_payload)

    target = settings.frontend_oauth_done_uri
    parsed = urlparse(target)
    query = dict(parse_qsl(parsed.query))
    query["email"] = user.email
    query["oauth"] = "success"
    redirect_url = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path or "/",
            parsed.params,
            urlencode(query),
            parsed.fragment,
        )
    )
    bridge_query = urlencode({"redirect": redirect_url})
    return RedirectResponse(url=f"/api/auth/complete?{bridge_query}", status_code=302)


@router.get("/auth/complete", response_class=HTMLResponse)
def auth_complete(redirect: str = Query(...)):
    safe_redirect = redirect.replace('"', "%22")
    return f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>OAuth Completed</title>
    <meta http-equiv="refresh" content="0;url={safe_redirect}" />
    <style>
      body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 24px; }}
      a {{ color: #2563eb; }}
    </style>
  </head>
  <body>
    <h2>Google sign-in completed</h2>
    <p>Redirecting to Smart Inbox...</p>
    <p>If the redirect does not happen automatically, click: <a href="{safe_redirect}">Continue to the app</a></p>
  </body>
</html>
"""


@router.get("/auth/status", response_model=AuthStatusResponse)
def auth_status(
    x_user_email: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
):
    if not x_user_email:
        return AuthStatusResponse(connected=False, email=None)
    user = db.query(User).filter(User.email == x_user_email.strip().lower()).first()
    if not user:
        return AuthStatusResponse(connected=False, email=None)
    token = db.query(OAuthToken).filter(OAuthToken.user_id == user.id).first()
    return AuthStatusResponse(connected=token is not None, email=user.email)


@router.get("/auth/debug-config", response_model=AuthConfigResponse)
def auth_debug_config():
    return AuthConfigResponse(
        google_client_id_configured=bool(settings.google_client_id),
        google_client_secret_configured=bool(settings.google_client_secret),
        google_redirect_uri=settings.google_redirect_uri,
    )


@router.post("/sync/run", response_model=MessageResponse)
def sync_run(
    payload: SyncRequest,
    x_user_email: Optional[str] = Header(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if x_user_email:
        created = sync_gmail_inbox(db, user, payload.seed_count)
        return MessageResponse(message=f"Synced {created} emails from Gmail.")

    created = seed_mock_emails(db, user, payload.seed_count, trim_to_count=payload.trim_to_count)
    return MessageResponse(message=f"Synced {created} demo emails.")


@router.get("/inbox", response_model=InboxResponse)
def get_inbox(
    bucket: str = Query("now"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = (
        db.query(Email)
        .filter(Email.user_id == user.id, Email.bucket == bucket)
        .order_by(Email.score.desc(), Email.received_at.desc())
        .limit(100)
        .all()
    )
    return InboxResponse(bucket=bucket, items=items)


@router.get("/emails/{email_id}", response_model=EmailDetail)
def get_email(
    email_id: int,
    mode: ViewMode = Query("busy"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    email = db.query(Email).filter(Email.id == email_id, Email.user_id == user.id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    if mode == "busy":
        email.body = ""

    return email


@router.post("/emails/{email_id}/feedback", response_model=MessageResponse)
def feedback(
    email_id: int,
    payload: FeedbackRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    email = db.query(Email).filter(Email.id == email_id, Email.user_id == user.id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    pref = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    if not pref:
        pref = UserPreference(user_id=user.id)
        db.add(pref)
        db.flush()

    important_senders = {s.strip().lower() for s in pref.important_senders.split(",") if s.strip()}
    muted_senders = {s.strip().lower() for s in pref.muted_senders.split(",") if s.strip()}
    sender = email.sender.lower()

    if payload.feedback_type == "important":
        important_senders.add(sender)
        muted_senders.discard(sender)
    elif payload.feedback_type == "mute_sender":
        muted_senders.add(sender)
        important_senders.discard(sender)
    elif payload.feedback_type == "remind_sender":
        important_senders.add(sender)
        muted_senders.discard(sender)

    pref.important_senders = ",".join(sorted(important_senders))
    pref.muted_senders = ",".join(sorted(muted_senders))

    db.add(
        InteractionEvent(
            user_id=user.id,
            email_id=email.id,
            event_type=payload.feedback_type,
            dwell_ms=0,
        )
    )

    rescore_user_emails(db, user, pref)
    db.commit()

    return MessageResponse(message="Feedback applied.")


@router.post("/events", response_model=MessageResponse)
def create_event(
    payload: EventRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    email = db.query(Email).filter(Email.id == payload.email_id, Email.user_id == user.id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    event = InteractionEvent(
        user_id=user.id,
        email_id=email.id,
        event_type=payload.event_type,
        dwell_ms=payload.dwell_ms,
    )
    db.add(event)

    if payload.event_type == "open":
        email.is_read = True

    pref = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    rescore_user_emails(db, user, pref)
    db.commit()
    return MessageResponse(message="Event recorded.")
