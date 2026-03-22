import base64
from datetime import datetime
from email.utils import parseaddr
from typing import Optional

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Email, User, UserPreference
from app.services.adaptation import rescore_user_emails
from app.services.auth import get_valid_access_token
from app.services.ranking import score_email
from app.services.summary import generate_busy_summary

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _gmail_get(client: httpx.Client, token: str, path: str, params: Optional[dict] = None) -> dict:
    res = client.get(
        f"{GMAIL_BASE}{path}",
        params=params or {},
        headers={"Authorization": f"Bearer {token}"},
    )
    if res.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Gmail API failed: {res.text}")
    return res.json()


def _decode_b64url(data: str) -> str:
    if not data:
        return ""
    padding = "=" * (-len(data) % 4)
    try:
        raw = base64.urlsafe_b64decode(data + padding)
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_plain_text(payload: dict) -> str:
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})
    data = body.get("data", "")
    if mime_type == "text/plain" and data:
        return _decode_b64url(data)

    for part in payload.get("parts", []) or []:
        text = _extract_plain_text(part)
        if text:
            return text
    return ""


def _has_attachment(payload: dict) -> bool:
    if payload.get("filename"):
        return True
    body = payload.get("body", {})
    if body.get("attachmentId"):
        return True
    for part in payload.get("parts", []) or []:
        if _has_attachment(part):
            return True
    return False


def _headers_to_map(headers: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for h in headers:
        name = (h.get("name") or "").strip()
        value = (h.get("value") or "").strip()
        if name:
            out[name.lower()] = value
    return out


def _extract_message_ids_from_history(history: list[dict]) -> list[str]:
    ids: set[str] = set()
    for row in history:
        for add in row.get("messagesAdded", []) or []:
            msg = add.get("message", {})
            mid = msg.get("id")
            if mid:
                ids.add(mid)
    return list(ids)


def sync_gmail_inbox(db: Session, user: User, max_results: int = 30) -> int:
    token = get_valid_access_token(db, user)
    pref = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()

    with httpx.Client(timeout=20) as client:
        profile = _gmail_get(client, token, "/profile")
        message_ids: list[str] = []

        if user.gmail_history_id:
            try:
                history_data = _gmail_get(
                    client,
                    token,
                    "/history",
                    params={
                        "startHistoryId": user.gmail_history_id,
                        "historyTypes": "messageAdded",
                        "maxResults": max_results,
                    },
                )
                message_ids = _extract_message_ids_from_history(history_data.get("history", []))
            except HTTPException:
                message_ids = []

        if not message_ids:
            listing = _gmail_get(
                client,
                token,
                "/messages",
                params={"labelIds": "INBOX", "maxResults": max_results},
            )
            message_ids = [m.get("id") for m in listing.get("messages", []) if m.get("id")]

    synced = 0
    for message_id in message_ids:
        with httpx.Client(timeout=20) as client:
            raw = _gmail_get(client, token, f"/messages/{message_id}", params={"format": "full"})

        payload = raw.get("payload", {}) or {}
        headers = _headers_to_map(payload.get("headers", []) or [])
        sender_raw = headers.get("from", "")
        sender = parseaddr(sender_raw)[1] or sender_raw or "unknown@unknown.local"
        subject = headers.get("subject", "(no subject)")
        to_raw = headers.get("to", "").lower()
        cc_raw = headers.get("cc", "").lower()
        user_email = user.email.lower()
        is_cc = user_email in cc_raw and user_email not in to_raw
        snippet = raw.get("snippet", "") or ""
        body = _extract_plain_text(payload) or snippet
        has_attachment = _has_attachment(payload)
        internal_ms = raw.get("internalDate")
        try:
            received_at = datetime.utcfromtimestamp(int(internal_ms) / 1000) if internal_ms else datetime.utcnow()
        except Exception:
            received_at = datetime.utcnow()
        word_count = len(body.split())

        existing = (
            db.query(Email)
            .filter(Email.user_id == user.id, Email.external_id == message_id)
            .first()
        )
        if existing:
            mail = existing
        else:
            mail = Email(user_id=user.id, external_id=message_id)
            db.add(mail)

        mail.thread_id = raw.get("threadId", "")
        mail.sender = sender[:255]
        mail.subject = subject[:512]
        mail.snippet = snippet
        mail.body = body
        mail.has_attachment = has_attachment
        mail.is_cc = is_cc
        mail.word_count = word_count
        mail.received_at = received_at

        score, bucket, needs_action = score_email(mail, pref)
        summary, action_items = generate_busy_summary(mail)
        mail.score = score
        mail.bucket = bucket
        mail.needs_action = needs_action
        mail.busy_summary = summary
        mail.action_items = action_items
        synced += 1

    user.gmail_history_id = str(profile.get("historyId")) if profile.get("historyId") else user.gmail_history_id
    if synced:
        db.flush()
        rescore_user_emails(db, user, pref)
    db.commit()
    return synced
