from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models import Email, InteractionEvent, SenderProfile, ThreadProfile, User, UserPreference
from app.services.ranking import ScoreContribution, bucket_for_score, clamp_score, score_email_explained
from app.services.user_model import ensure_profiles_backfilled, get_feature_weights


@dataclass
class EmailInteractionSummary:
    opened: bool = False
    quick_close_count: int = 0
    reply_count: int = 0
    latest_priority_feedback: Optional[str] = None


@dataclass
class AdaptationContext:
    interaction_summaries: dict[int, EmailInteractionSummary]
    sender_profiles: dict[str, SenderProfile]
    thread_profiles: dict[str, ThreadProfile]


@dataclass
class AdaptiveScoreResult:
    score: float
    bucket: str
    needs_action: bool
    breakdown: list[ScoreContribution]
    reason_summary: str
    model_summary: str


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


def build_adaptation_context(db: Session, user: User) -> AdaptationContext:
    ensure_profiles_backfilled(db, user)
    events = (
        db.query(InteractionEvent)
        .filter(InteractionEvent.user_id == user.id)
        .order_by(InteractionEvent.created_at.asc(), InteractionEvent.id.asc())
        .all()
    )
    interaction_summaries = _collect_interaction_summaries(events)
    sender_profiles = {
        profile.sender: profile
        for profile in db.query(SenderProfile).filter(SenderProfile.user_id == user.id).all()
    }
    thread_profiles = {
        profile.thread_id: profile
        for profile in db.query(ThreadProfile).filter(ThreadProfile.user_id == user.id).all()
    }
    return AdaptationContext(
        interaction_summaries=interaction_summaries,
        sender_profiles=sender_profiles,
        thread_profiles=thread_profiles,
    )


def _format_reason_label(label: str) -> str:
    cleaned = label.strip()
    if cleaned.lower().startswith("learned "):
        cleaned = cleaned[8:]
    return cleaned


def _reason_summary(breakdown: list[ScoreContribution]) -> str:
    ranked = sorted(
        (item for item in breakdown if item.label != "Base score"),
        key=lambda item: abs(item.value),
        reverse=True,
    )
    if not ranked:
        return "Mostly baseline ranking."
    labels = [_format_reason_label(item.label) for item in ranked[:2]]
    return " + ".join(labels)


def _model_summary(breakdown: list[ScoreContribution]) -> str:
    positives = [
        _format_reason_label(item.label)
        for item in sorted(breakdown, key=lambda item: item.value, reverse=True)
        if item.value > 0 and item.label != "Base score"
    ][:2]
    negatives = [
        _format_reason_label(item.label)
        for item in sorted(breakdown, key=lambda item: item.value)
        if item.value < 0
    ][:2]

    parts: list[str] = []
    if positives:
        parts.append(f"Ranking raised by {', '.join(positives)}")
    if negatives:
        parts.append(f"held back by {', '.join(negatives)}")
    return ". ".join(parts) + ("." if parts else "")


def compute_adaptive_score(
    email: Email,
    preference: Optional[UserPreference],
    summary: Optional[EmailInteractionSummary] = None,
    sender_profile: Optional[SenderProfile] = None,
    thread_profile: Optional[ThreadProfile] = None,
) -> AdaptiveScoreResult:
    base_result = score_email_explained(email, preference, sender_profile, thread_profile)
    score = base_result.score
    breakdown = list(base_result.breakdown)
    weights = get_feature_weights(preference)

    if summary:
        if summary.latest_priority_feedback == "important":
            bonus = 0.30
            score += bonus
            breakdown.append(
                ScoreContribution(
                    label="Marked important",
                    value=bonus,
                    detail="You explicitly marked this email as important.",
                    source="explicit",
                )
            )
        elif summary.latest_priority_feedback == "not_important":
            penalty = -0.38
            score += penalty
            breakdown.append(
                ScoreContribution(
                    label="Marked not important",
                    value=penalty,
                    detail="You explicitly marked this email as not important.",
                    source="explicit",
                )
            )

        if summary.opened:
            bonus = weights["opened_bonus"]
            score += bonus
            breakdown.append(
                ScoreContribution(
                    label="Previously opened",
                    value=bonus,
                    detail="Opening an email is treated as a weak signal of relevance.",
                    source="behavior",
                )
            )
        if summary.quick_close_count:
            penalty = -weights["quick_close_penalty"] * min(summary.quick_close_count, 2)
            score += penalty
            breakdown.append(
                ScoreContribution(
                    label="Quick-close history",
                    value=penalty,
                    detail="Leaving this email quickly lowers its future priority.",
                    source="behavior",
                )
            )
        if summary.reply_count:
            bonus = weights["reply_bonus"] * min(summary.reply_count, 2)
            score += bonus
            breakdown.append(
                ScoreContribution(
                    label="Reply history",
                    value=bonus,
                    detail="Threads that led to a reply are treated as stronger work signals.",
                    source="behavior",
                )
            )

    score = clamp_score(score)
    bucket = bucket_for_score(score)
    reason_summary = _reason_summary(breakdown)
    model_summary = _model_summary(breakdown)
    return AdaptiveScoreResult(
        score=score,
        bucket=bucket,
        needs_action=base_result.needs_action,
        breakdown=sorted(breakdown, key=lambda item: abs(item.value), reverse=True),
        reason_summary=reason_summary,
        model_summary=model_summary,
    )


def rescore_user_emails(
    db: Session, user: User, preference: Optional[UserPreference] = None
) -> list[Email]:
    db.flush()

    if preference is None:
        preference = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()

    emails = db.query(Email).filter(Email.user_id == user.id).all()
    if not emails:
        return []

    context = build_adaptation_context(db, user)

    for email in emails:
        sender_profile = context.sender_profiles.get(email.sender.lower())
        thread_profile = context.thread_profiles.get(email.thread_id)
        result = compute_adaptive_score(
            email=email,
            preference=preference,
            summary=context.interaction_summaries.get(email.id),
            sender_profile=sender_profile,
            thread_profile=thread_profile,
        )
        email.score = result.score
        email.bucket = result.bucket
        email.needs_action = result.needs_action

    return emails
