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
    EmailListItem,
    EventRequest,
    FeedbackRequest,
    FeatureWeightItem,
    InboxResponse,
    InteractionSummaryResponse,
    MessageResponse,
    ScoreBreakdownItem,
    SendEmailRequest,
    SyncRequest,
    UserModelResponse,
    UserModelUpdateRequest,
    ThreadContextResponse,
    ThreadMessageItem,
    ViewMode,
)
from app.services.gmail_send import send_gmail_message
from app.services.adaptation import (
    build_adaptation_context,
    compute_adaptive_score,
    describe_personalization_signals,
    rescore_user_emails,
)
from app.services.gmail_sync import sync_gmail_inbox
from app.services.summary import generate_busy_summary, summary_needs_refresh
from app.services.sync import ensure_demo_user, seed_mock_emails
from app.services.auth import (
    build_google_auth_url,
    create_oauth_state,
    ensure_oauth_config,
    exchange_code_for_tokens,
    fetch_google_userinfo,
    get_valid_access_token,
    has_gmail_send_scope,
    upsert_user_and_token,
    validate_state,
)
from app.services.user_model import (
    build_user_model_snapshot,
    ensure_user_preference,
    record_interaction,
    set_sender_preferences,
    update_feature_weights,
)

router = APIRouter()


def _client_identity_email(
    x_user_email: Optional[str], user_email_query: Optional[str]
) -> Optional[str]:
    """Prefer header; some environments drop custom headers on GET — query is a fallback."""
    combined = (x_user_email or user_email_query or "").strip()
    return combined.lower() if combined else None


def get_current_user(
    db: Session = Depends(get_db),
    x_user_email: Optional[str] = Header(default=None),
    user_email: Optional[str] = Query(
        default=None,
        description="Fallback for X-User-Email (e.g. when custom headers are stripped on GET).",
    ),
):
    email = _client_identity_email(x_user_email, user_email)
    if not email:
        return ensure_demo_user(db)

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
    user_email: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    ident = _client_identity_email(x_user_email, user_email)
    if not ident:
        return AuthStatusResponse(connected=False, email=None, can_send=False)
    user = db.query(User).filter(User.email == ident).first()
    if not user:
        return AuthStatusResponse(connected=False, email=None, can_send=False)
    token = db.query(OAuthToken).filter(OAuthToken.user_id == user.id).first()
    if not token:
        return AuthStatusResponse(connected=False, email=user.email, can_send=False)
    try:
        get_valid_access_token(db, user)
    except HTTPException:
        return AuthStatusResponse(connected=False, email=user.email, can_send=False)
    return AuthStatusResponse(
        connected=True,
        email=user.email,
        can_send=has_gmail_send_scope(token.scope),
    )


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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Gmail when this user has OAuth tokens (identity from header and/or user_email query).
    token = db.query(OAuthToken).filter(OAuthToken.user_id == user.id).first()
    if token:
        created = sync_gmail_inbox(db, user, payload.seed_count)
        return MessageResponse(message=f"Synced {created} emails from Gmail.")

    created = seed_mock_emails(db, user, payload.seed_count, trim_to_count=payload.trim_to_count)
    return MessageResponse(message=f"Synced {created} demo emails.")


@router.get("/inbox", response_model=InboxResponse)
def get_inbox(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    bucket: str = Query("now"),
    view: str = Query(
        "busy",
        description="busy = filter by priority zone; normal = all messages (newest first), zones ignored",
    ),
    all_messages: bool = Query(
        False,
        description="Explicit Normal list: all messages by date (avoids empty UI if view is misread).",
    ),
):
    view_key = (view or "").strip().lower()
    if view_key not in ("busy", "normal"):
        raise HTTPException(status_code=400, detail="view must be 'busy' or 'normal'.")
    allowed_buckets = {"now", "read", "skim", "later"}
    if bucket not in allowed_buckets:
        raise HTTPException(status_code=400, detail="Invalid bucket.")

    # Normal: full list. Gmail mail often lands in "later"; Busy+now would return [] while sync says 24.
    if all_messages or view_key == "normal":
        items = (
            db.query(Email)
            .filter(Email.user_id == user.id)
            .order_by(Email.received_at.desc())
            .limit(200)
            .all()
        )
        # Normal list is "read everything by date" — skip adaptive rescoring per row (was O(n)
        # and could take minutes for large inboxes). Busy mode still computes live reasons.
        return InboxResponse(
            bucket=bucket,
            items=[
                EmailListItem(
                    id=email.id,
                    thread_id=email.thread_id or "",
                    sender=email.sender,
                    subject=email.subject,
                    snippet=email.snippet,
                    has_attachment=email.has_attachment,
                    is_cc=email.is_cc,
                    received_at=email.received_at,
                    score=email.score,
                    bucket=email.bucket,
                    needs_action=email.needs_action,
                    reason_summary="",
                )
                for email in items
            ],
        )

    preference = ensure_user_preference(db, user)
    items = (
        db.query(Email)
        .filter(Email.user_id == user.id, Email.bucket == bucket)
        .order_by(Email.score.desc(), Email.received_at.desc())
        .limit(100)
        .all()
    )
    context = build_adaptation_context(db, user)
    response_items = []
    for email in items:
        result = compute_adaptive_score(
            email=email,
            preference=preference,
            summary=context.interaction_summaries.get(email.id),
            sender_profile=context.sender_profiles.get(email.sender.lower()),
            thread_profile=context.thread_profiles.get(email.thread_id),
        )
        response_items.append(
            EmailListItem(
                id=email.id,
                thread_id=email.thread_id or "",
                sender=email.sender,
                subject=email.subject,
                snippet=email.snippet,
                has_attachment=email.has_attachment,
                is_cc=email.is_cc,
                received_at=email.received_at,
                score=email.score,
                bucket=email.bucket,
                needs_action=email.needs_action,
                reason_summary=result.reason_summary,
            )
        )
    return InboxResponse(bucket=bucket, items=response_items)


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
    preference = ensure_user_preference(db, user)
    full_body = email.body

    if mode == "busy":
        if summary_needs_refresh(email):
            summary, action_items = generate_busy_summary(email)
            email.busy_summary = summary
            email.action_items = action_items
            db.commit()
            db.refresh(email)
            full_body = email.body
        email.body = ""

    email_for_scoring = email
    if full_body and email.body != full_body:
        email.body = full_body
    context = build_adaptation_context(db, user)
    result = compute_adaptive_score(
        email=email_for_scoring,
        preference=preference,
        summary=context.interaction_summaries.get(email.id),
        sender_profile=context.sender_profiles.get(email.sender.lower()),
        thread_profile=context.thread_profiles.get(email.thread_id),
    )
        manual_signals, observed_signals = describe_personalization_signals(
            email=email_for_scoring,
            preference=preference,
            summary=context.interaction_summaries.get(email.id),
            sender_profile=context.sender_profiles.get(email.sender.lower()),
            thread_profile=context.thread_profiles.get(email.thread_id),
        )
    return EmailDetail(
        id=email.id,
        thread_id=email.thread_id,
        sender=email.sender,
        subject=email.subject,
        snippet=email.snippet,
        has_attachment=email.has_attachment,
        is_cc=email.is_cc,
        received_at=email.received_at,
        score=result.score,
        bucket=result.bucket,
        needs_action=result.needs_action,
        body="" if mode == "busy" else full_body,
        busy_summary=email.busy_summary,
        action_items=email.action_items,
        reason_summary=result.reason_summary,
        model_summary=result.model_summary,
        score_breakdown=[
            ScoreBreakdownItem(
                label=item.label,
                value=round(float(item.value), 4),
                detail=item.detail,
                source=item.source,
            )
            for item in result.breakdown
        ],
        manual_signals=manual_signals,
        observed_signals=observed_signals,
    )


@router.post("/mail/send", response_model=MessageResponse)
def send_email(
    payload: SendEmailRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token = db.query(OAuthToken).filter(OAuthToken.user_id == user.id).first()
    if not token:
        raise HTTPException(status_code=401, detail="Connect Gmail to send messages.")
    if not has_gmail_send_scope(token.scope):
        raise HTTPException(
            status_code=403,
            detail="Gmail send permission is not granted. Reconnect Gmail and approve send access.",
        )

    reply_to_email = None
    if payload.reply_to_email_id is not None:
        reply_to_email = (
            db.query(Email)
            .filter(Email.id == payload.reply_to_email_id, Email.user_id == user.id)
            .first()
        )
        if not reply_to_email:
            raise HTTPException(status_code=404, detail="Reply target email not found")

    send_gmail_message(
        db=db,
        user=user,
        to=payload.to,
        cc=payload.cc,
        subject=payload.subject,
        body=payload.body,
        reply_to_email=reply_to_email,
    )

    return MessageResponse(message="Email sent.")


@router.get("/emails/{email_id}/thread", response_model=ThreadContextResponse)
def get_email_thread(
    email_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    email = db.query(Email).filter(Email.id == email_id, Email.user_id == user.id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    rows = (
        db.query(Email)
        .filter(Email.user_id == user.id, Email.thread_id == email.thread_id)
        .order_by(Email.received_at.asc())
        .all()
    )
    messages = [
        ThreadMessageItem(
            id=row.id,
            sender=row.sender,
            subject=row.subject,
            snippet=row.snippet,
            received_at=row.received_at,
        )
        for row in rows
    ]
    return ThreadContextResponse(
        thread_id=email.thread_id,
        current_email_id=email.id,
        messages=messages,
    )


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

    pref = ensure_user_preference(db, user)

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
    record_interaction(db, user, email, payload.feedback_type)

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
    record_interaction(db, user, email, payload.event_type)

    if payload.event_type == "open":
        email.is_read = True

    pref = ensure_user_preference(db, user)
    rescore_user_emails(db, user, pref)
    db.commit()
    return MessageResponse(message="Event recorded.")


@router.get("/model", response_model=UserModelResponse)
def get_user_model(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    preference = ensure_user_preference(db, user)
    snapshot = build_user_model_snapshot(db, user, preference)
    return UserModelResponse(
        email=str(snapshot["email"]),
        important_senders=list(snapshot["important_senders"]),
        muted_senders=list(snapshot["muted_senders"]),
        feature_weights=[FeatureWeightItem(**item) for item in snapshot["feature_weights"]],
        sender_profiles=list(snapshot["sender_profiles"]),
        thread_profiles=list(snapshot["thread_profiles"]),
        interaction_summary=InteractionSummaryResponse(**snapshot["interaction_summary"]),
        scrutability_notes=list(snapshot["scrutability_notes"]),
        recent_learning_events=list(snapshot["recent_learning_events"]),
    )


@router.put("/model", response_model=UserModelResponse)
def update_user_model(
    payload: UserModelUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    preference = ensure_user_preference(db, user)
    set_sender_preferences(
        preference,
        important=payload.important_senders,
        muted=payload.muted_senders,
    )
    update_feature_weights(preference, payload.feature_weights)
    rescore_user_emails(db, user, preference)
    db.commit()
    snapshot = build_user_model_snapshot(db, user, preference)
    return UserModelResponse(
        email=str(snapshot["email"]),
        important_senders=list(snapshot["important_senders"]),
        muted_senders=list(snapshot["muted_senders"]),
        feature_weights=[FeatureWeightItem(**item) for item in snapshot["feature_weights"]],
        sender_profiles=list(snapshot["sender_profiles"]),
        thread_profiles=list(snapshot["thread_profiles"]),
        interaction_summary=InteractionSummaryResponse(**snapshot["interaction_summary"]),
        scrutability_notes=list(snapshot["scrutability_notes"]),
        recent_learning_events=list(snapshot["recent_learning_events"]),
    )
