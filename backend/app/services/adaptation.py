from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models import Email, InteractionEvent, User, UserPreference
from app.services.ranking import bucket_for_score, clamp_score, score_email


@dataclass
class EmailInteractionSummary:
    opened: bool = False
    quick_close_count: int = 0
    reply_count: int = 0
    latest_priority_feedback: Optional[str] = None


def _collect_interaction_summaries(
    events: Iterable[InteractionEvent],
) -> dict[int, EmailInteractionSummary]:
    summaries: dict[int, EmailInteractionSummary] = {}
    for event in events:
        summary = summaries.setdefault(event.email_id, EmailInteractionSummary())
        if event.event_type == "open":
            summary.opened = True
        elif event.event_type == "quick_close":
            summary.quick_close_count += 1
        elif event.event_type == "reply":
            summary.reply_count += 1
        elif event.event_type in {"important", "not_important"}:
            summary.latest_priority_feedback = event.event_type
    return summaries


def apply_adaptive_adjustments(
    base_score: float, summary: Optional[EmailInteractionSummary]
) -> float:
    if not summary:
        return base_score

    adjustment = 0.0
    if summary.latest_priority_feedback == "important":
        adjustment += 0.35
    elif summary.latest_priority_feedback == "not_important":
        adjustment -= 0.45

    if summary.opened:
        adjustment += 0.03
    adjustment -= 0.08 * min(summary.quick_close_count, 2)
    adjustment += 0.12 * min(summary.reply_count, 2)
    return clamp_score(base_score + adjustment)


def rescore_user_emails(
    db: Session, user: User, preference: Optional[UserPreference] = None
) -> list[Email]:
    db.flush()

    if preference is None:
        preference = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()

    emails = db.query(Email).filter(Email.user_id == user.id).all()
    if not emails:
        return []

    events = (
        db.query(InteractionEvent)
        .filter(InteractionEvent.user_id == user.id)
        .order_by(InteractionEvent.created_at.asc(), InteractionEvent.id.asc())
        .all()
    )
    summaries = _collect_interaction_summaries(events)

    for email in emails:
        base_score, _, needs_action = score_email(email, preference)
        adjusted_score = apply_adaptive_adjustments(base_score, summaries.get(email.id))
        email.score = adjusted_score
        email.bucket = bucket_for_score(adjusted_score)
        email.needs_action = needs_action

    return emails
