import base64
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Optional

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Email, User
from app.services.auth import get_valid_access_token

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _gmail_post(client: httpx.Client, token: str, path: str, payload: dict) -> dict:
    res = client.post(
        f"{GMAIL_BASE}{path}",
        json=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    if res.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Gmail API failed: {res.text}")
    return res.json()


def _gmail_get_metadata(client: httpx.Client, token: str, external_id: str) -> dict:
    res = client.get(
        f"{GMAIL_BASE}/messages/{external_id}",
        params={
            "format": "metadata",
            "metadataHeaders": ["Message-ID", "References"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    if res.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"Gmail API failed: {res.text}")
    return res.json()


def _parse_recipients(value: str, field_name: str) -> list[str]:
    raw_parts = [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]
    recipients: list[str] = []
    seen: set[str] = set()

    for raw_part in raw_parts:
        display_name, address = parseaddr(raw_part)
        normalized = address.strip().lower()
        if not normalized or "@" not in normalized:
            raise HTTPException(status_code=400, detail=f"Invalid {field_name} recipient: {raw_part}")
        if normalized in seen:
            continue
        seen.add(normalized)
        recipients.append(formataddr((display_name, address.strip())) if display_name else address.strip())

    return recipients


def _reply_headers(client: httpx.Client, token: str, email: Email) -> tuple[str, str]:
    if not email.external_id or email.external_id.startswith("mock-"):
        return "", ""

    metadata = _gmail_get_metadata(client, token, email.external_id)
    headers = {
        (header.get("name") or "").strip().lower(): (header.get("value") or "").strip()
        for header in metadata.get("payload", {}).get("headers", []) or []
    }
    message_id = headers.get("message-id", "")
    references = headers.get("references", "")
    return message_id, references


def send_gmail_message(
    db: Session,
    user: User,
    to: str,
    cc: str = "",
    subject: str = "",
    body: str = "",
    reply_to_email: Optional[Email] = None,
) -> dict:
    to_recipients = _parse_recipients(to, "To")
    cc_recipients = _parse_recipients(cc, "Cc")
    if not to_recipients:
        raise HTTPException(status_code=400, detail="At least one To recipient is required.")

    token = get_valid_access_token(db, user)

    message = EmailMessage()
    message["From"] = user.email
    message["To"] = ", ".join(to_recipients)
    if cc_recipients:
        message["Cc"] = ", ".join(cc_recipients)
    message["Subject"] = subject.strip() or "(no subject)"

    payload: dict[str, str] = {}
    with httpx.Client(timeout=20) as client:
        if reply_to_email:
            message_id, references = _reply_headers(client, token, reply_to_email)
            if message_id:
                message["In-Reply-To"] = message_id
                reference_value = " ".join(part for part in [references, message_id] if part).strip()
                if reference_value:
                    message["References"] = reference_value
            if reply_to_email.thread_id:
                payload["threadId"] = reply_to_email.thread_id

        message.set_content(body or "")
        payload["raw"] = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        return _gmail_post(client, token, "/messages/send", payload)
