from typing import Optional

from app.models import Email, UserPreference


ACTION_HINTS = ["deadline", "confirm", "urgent", "action required", "please review"]


def _split_csv(raw: str) -> set[str]:
    return {v.strip().lower() for v in raw.split(",") if v.strip()}


def score_email(email: Email, preference: Optional[UserPreference]) -> tuple[float, str, bool]:
    score = 0.1

    muted = set()
    important = set()
    long_penalty = 0.15
    if preference:
        muted = _split_csv(preference.muted_senders)
        important = _split_csv(preference.important_senders)
        long_penalty = preference.long_email_penalty

    sender_l = email.sender.lower()
    text = f"{email.subject} {email.snippet}".lower()
    needs_action = any(h in text for h in ACTION_HINTS)

    if sender_l in muted:
        score -= 0.6
    if sender_l in important:
        score += 0.4
    if not email.is_cc:
        score += 0.1
    if email.has_attachment:
        score += 0.08
    if needs_action:
        score += 0.32
    if email.word_count > 350:
        score -= long_penalty

    score = max(0.0, min(1.0, score))

    if score >= 0.75:
        bucket = "now"
    elif score >= 0.5:
        bucket = "read"
    elif score >= 0.3:
        bucket = "skim"
    else:
        bucket = "later"

    return score, bucket, needs_action
