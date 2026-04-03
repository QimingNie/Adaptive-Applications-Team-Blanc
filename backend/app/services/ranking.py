from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from app.models import Email, SenderProfile, ThreadProfile, UserPreference
from app.services.user_model import (
    get_feature_weights,
    important_senders,
    muted_senders,
    sender_affinity,
    thread_affinity,
)

ACTION_HINTS = ["deadline", "confirm", "urgent", "action required", "please review", "due", "by noon"]
QUESTION_HINTS = ["can you", "could you", "would you", "?", "what do you think"]
REPLY_HINTS = ["reply", "respond", "let me know", "confirm", "send me", "follow up"]


@dataclass
class ScoreContribution:
    label: str
    value: float
    detail: str
    source: str


@dataclass
class ScoreResult:
    score: float
    bucket: str
    needs_action: bool
    breakdown: list[ScoreContribution]


def _split_csv(raw: str) -> set[str]:
    return {v.strip().lower() for v in raw.split(",") if v.strip()}


def clamp_score(score: float) -> float:
    return max(0.0, min(1.0, score))


def bucket_for_score(score: float) -> str:
    if score >= 0.75:
        return "now"
    if score >= 0.5:
        return "read"
    if score >= 0.3:
        return "skim"
    return "later"


def score_email(
    email: Email,
    preference: Optional[UserPreference],
    sender_profile: Optional[SenderProfile] = None,
    thread_profile: Optional[ThreadProfile] = None,
) -> tuple[float, str, bool]:
    result = score_email_explained(email, preference, sender_profile, thread_profile)
    return result.score, result.bucket, result.needs_action


def score_email_explained(
    email: Email,
    preference: Optional[UserPreference],
    sender_profile: Optional[SenderProfile] = None,
    thread_profile: Optional[ThreadProfile] = None,
    now: Optional[datetime] = None,
) -> ScoreResult:
    now = now or datetime.utcnow()
    weights = get_feature_weights(preference)
    sender_l = email.sender.lower()
    text = f"{email.subject} {email.snippet} {email.body}".lower()
    needs_action = any(h in text for h in ACTION_HINTS)
    has_question_signal = any(h in text for h in QUESTION_HINTS)
    has_reply_signal = any(h in text for h in REPLY_HINTS)
    score = 0.1
    breakdown = [
        ScoreContribution(
            label="Base score",
            value=0.10,
            detail="All emails start from the same baseline before adaptation.",
            source="baseline",
        )
    ]

    important = set(important_senders(preference))
    muted = set(muted_senders(preference))
    if sender_l in muted:
        penalty = -weights["muted_sender_penalty"]
        score += penalty
        breakdown.append(
            ScoreContribution(
                label="Muted sender",
                value=penalty,
                detail="This sender is explicitly muted in the user model.",
                source="explicit",
            )
        )
    if sender_l in important:
        bonus = weights["important_sender_bonus"]
        score += bonus
        breakdown.append(
            ScoreContribution(
                label="Important sender",
                value=bonus,
                detail="This sender is explicitly marked as important.",
                source="explicit",
            )
        )

    if not email.is_cc:
        bonus = weights["direct_bonus"]
        score += bonus
        breakdown.append(
            ScoreContribution(
                label="Direct email",
                value=bonus,
                detail="Direct messages are generally treated as more relevant than CCs.",
                source="content",
            )
        )
    if email.has_attachment:
        bonus = weights["attachment_bonus"]
        score += bonus
        breakdown.append(
            ScoreContribution(
                label="Attachment included",
                value=bonus,
                detail="Attachments often indicate work artefacts or supporting material.",
                source="content",
            )
        )
    if needs_action:
        bonus = weights["action_keyword_bonus"]
        score += bonus
        breakdown.append(
            ScoreContribution(
                label="Action language",
                value=bonus,
                detail="The subject or preview contains deadline or action-oriented language.",
                source="content",
            )
        )
    if has_question_signal:
        bonus = weights["question_bonus"]
        score += bonus
        breakdown.append(
            ScoreContribution(
                label="Question signal",
                value=bonus,
                detail="Questions are often a strong indicator that a response is needed.",
                source="content",
            )
        )
    if has_reply_signal:
        bonus = weights["reply_signal_bonus"]
        score += bonus
        breakdown.append(
            ScoreContribution(
                label="Reply signal",
                value=bonus,
                detail="The wording suggests that a reply or confirmation is expected.",
                source="content",
            )
        )

    age_hours = max(0.0, (now - email.received_at).total_seconds() / 3600)
    if age_hours < 72:
        recency_factor = max(0.0, 1.0 - (age_hours / 72.0))
        bonus = weights["recency_bonus"] * recency_factor
        if bonus > 0:
            score += bonus
            breakdown.append(
                ScoreContribution(
                    label="Fresh email",
                    value=bonus,
                    detail="Newer emails get a gentle boost so fresh work stays visible.",
                    source="context",
                )
            )

    if email.word_count > 350:
        penalty_scale = min(1.5, email.word_count / 350)
        penalty = -weights["long_email_penalty"] * penalty_scale
        score += penalty
        breakdown.append(
            ScoreContribution(
                label="Long message",
                value=penalty,
                detail="Long emails are penalized because they take more effort to process quickly.",
                source="content",
            )
        )

    sender_score = weights["sender_affinity_scale"] * sender_affinity(sender_profile)
    if abs(sender_score) > 0.01:
        score += sender_score
        breakdown.append(
            ScoreContribution(
                label="Learned sender affinity",
                value=sender_score,
                detail="Past opens, replies, and feedback for this sender adjust the ranking.",
                source="implicit",
            )
        )

    thread_score = weights["thread_affinity_scale"] * thread_affinity(thread_profile)
    if abs(thread_score) > 0.01:
        score += thread_score
        breakdown.append(
            ScoreContribution(
                label="Learned thread affinity",
                value=thread_score,
                detail="Past interactions with this thread adjust how prominently it is shown.",
                source="implicit",
            )
        )

    score = clamp_score(score)
    return ScoreResult(score=score, bucket=bucket_for_score(score), needs_action=needs_action, breakdown=breakdown)
