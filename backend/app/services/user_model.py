import json
from collections import defaultdict
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Email,
    InteractionEvent,
    SenderProfile,
    ThreadProfile,
    User,
    UserPreference,
)

DEFAULT_LONG_EMAIL_PENALTY = 0.15

FEATURE_WEIGHT_METADATA = [
    {
        "key": "important_sender_bonus",
        "label": "Important Sender Boost",
        "description": "How much explicitly marked important senders are promoted.",
        "default": 0.40,
    },
    {
        "key": "muted_sender_penalty",
        "label": "Muted Sender Penalty",
        "description": "How strongly muted senders are pushed down.",
        "default": 0.60,
    },
    {
        "key": "direct_bonus",
        "label": "Direct Email Boost",
        "description": "Boost for messages sent directly to you instead of CC.",
        "default": 0.10,
    },
    {
        "key": "attachment_bonus",
        "label": "Attachment Boost",
        "description": "Boost for messages that include attachments.",
        "default": 0.08,
    },
    {
        "key": "action_keyword_bonus",
        "label": "Action Phrase Boost",
        "description": "Boost for emails that look action-oriented or deadline-driven.",
        "default": 0.32,
    },
    {
        "key": "question_bonus",
        "label": "Question Boost",
        "description": "Boost for messages that ask clear questions.",
        "default": 0.06,
    },
    {
        "key": "reply_signal_bonus",
        "label": "Reply Signal Boost",
        "description": "Boost for messages that explicitly ask for a response or confirmation.",
        "default": 0.10,
    },
    {
        "key": "recency_bonus",
        "label": "Recency Boost",
        "description": "Boost for newer emails so fresh work stays visible.",
        "default": 0.10,
    },
    {
        "key": "long_email_penalty",
        "label": "Long Email Penalty",
        "description": "Penalty for long emails that are harder to process quickly.",
        "default": DEFAULT_LONG_EMAIL_PENALTY,
    },
    {
        "key": "opened_bonus",
        "label": "Opened Email Boost",
        "description": "How much previously opened emails are nudged upward.",
        "default": 0.03,
    },
    {
        "key": "quick_close_penalty",
        "label": "Quick Close Penalty",
        "description": "Penalty when you leave an email quickly after opening it.",
        "default": 0.08,
    },
    {
        "key": "reply_bonus",
        "label": "Reply Boost",
        "description": "Boost when a thread already led to a reply.",
        "default": 0.12,
    },
    {
        "key": "sender_affinity_scale",
        "label": "Learned Sender Affinity",
        "description": "How much learned sender preferences affect ranking.",
        "default": 0.22,
    },
    {
        "key": "thread_affinity_scale",
        "label": "Learned Thread Affinity",
        "description": "How much learned thread preferences affect ranking.",
        "default": 0.16,
    },
]

DEFAULT_FEATURE_WEIGHTS = {
    item["key"]: float(item["default"])
    for item in FEATURE_WEIGHT_METADATA
    if item["key"] != "long_email_penalty"
}
EDITABLE_WEIGHT_KEYS = {item["key"] for item in FEATURE_WEIGHT_METADATA}
PROFILE_COUNT_FIELDS = (
    "open_count",
    "quick_close_count",
    "reply_count",
    "important_count",
    "not_important_count",
    "mute_count",
    "remind_count",
)

OBSERVED_EVENT_TYPES = {"open", "quick_close", "reply"}
POSITIVE_EVENT_TYPES = {"open", "reply", "important", "remind_sender"}
NEGATIVE_EVENT_TYPES = {"quick_close", "not_important", "mute_sender"}


def _split_csv(raw: str) -> list[str]:
    return [value.strip().lower() for value in raw.split(",") if value.strip()]


def _join_csv(values: list[str]) -> str:
    cleaned = sorted({value.strip().lower() for value in values if value.strip()})
    return ",".join(cleaned)


def interaction_event_origin(event_type: str) -> str:
    return "observed" if event_type in OBSERVED_EVENT_TYPES else "manual"


def interaction_event_impact(event_type: str) -> str:
    if event_type in POSITIVE_EVENT_TYPES:
        return "positive"
    if event_type in NEGATIVE_EVENT_TYPES:
        return "negative"
    return "neutral"


def interaction_event_label(event_type: str) -> str:
    labels = {
        "open": "Opened email",
        "quick_close": "Quick close",
        "reply": "Replied",
        "important": "Marked important",
        "not_important": "Marked not important",
        "mute_sender": "Muted sender",
        "remind_sender": "Remind later",
    }
    return labels.get(event_type, event_type.replace("_", " ").title())


def interaction_event_detail(event_type: str, dwell_ms: int = 0) -> str:
    if event_type == "open":
        return "Opening an email is treated as a light positive signal."
    if event_type == "quick_close":
        if dwell_ms > 0:
            seconds = max(0.1, dwell_ms / 1000)
            return f"Left after {seconds:.1f}s, which counts as a negative signal."
        return "Leaving a message quickly after opening counts as a negative signal."
    if event_type == "reply":
        return "Replying is treated as a strong positive signal for the sender and thread."
    if event_type == "important":
        return "You explicitly promoted this email for future ranking."
    if event_type == "not_important":
        return "You explicitly lowered the priority of similar emails."
    if event_type == "mute_sender":
        return "You explicitly deprioritized this sender."
    if event_type == "remind_sender":
        return "You asked the system to keep this sender more visible for follow-up."
    return "This interaction contributes to personalization over time."


def ensure_user_preference(db: Session, user: User) -> UserPreference:
    preference = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    if preference:
        return preference
    preference = UserPreference(user_id=user.id)
    db.add(preference)
    db.flush()
    return preference


def get_feature_weights(preference: Optional[UserPreference]) -> dict[str, float]:
    weights = dict(DEFAULT_FEATURE_WEIGHTS)
    weights["long_email_penalty"] = DEFAULT_LONG_EMAIL_PENALTY
    if not preference:
        return weights

    raw = preference.feature_weights_json.strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                for key, value in parsed.items():
                    if key in DEFAULT_FEATURE_WEIGHTS:
                        try:
                            weights[key] = max(0.0, min(2.0, float(value)))
                        except (TypeError, ValueError):
                            continue
        except json.JSONDecodeError:
            pass

    weights["long_email_penalty"] = max(0.0, min(2.0, float(preference.long_email_penalty)))
    return weights


def update_feature_weights(preference: UserPreference, updates: dict[str, float]) -> None:
    current = get_feature_weights(preference)
    for key, value in updates.items():
        if key not in EDITABLE_WEIGHT_KEYS:
            continue
        try:
            current[key] = max(0.0, min(2.0, float(value)))
        except (TypeError, ValueError):
            continue

    preference.long_email_penalty = current["long_email_penalty"]
    preference.feature_weights_json = json.dumps(
        {
            key: current[key]
            for key in sorted(DEFAULT_FEATURE_WEIGHTS)
        },
        sort_keys=True,
    )


def important_senders(preference: Optional[UserPreference]) -> list[str]:
    if not preference:
        return []
    return _split_csv(preference.important_senders)


def muted_senders(preference: Optional[UserPreference]) -> list[str]:
    if not preference:
        return []
    return _split_csv(preference.muted_senders)


def set_sender_preferences(
    preference: UserPreference,
    important: Optional[list[str]] = None,
    muted: Optional[list[str]] = None,
) -> None:
    if important is not None:
        preference.important_senders = _join_csv(important)
    if muted is not None:
        preference.muted_senders = _join_csv(muted)


def sender_affinity(profile: Optional[SenderProfile]) -> float:
    if not profile:
        return 0.0
    _normalize_profile_counts(profile)
    positive = (
        1.6 * profile.important_count
        + 1.0 * profile.remind_count
        + 1.2 * profile.reply_count
        + 0.25 * min(profile.open_count, 6)
    )
    negative = (
        1.3 * profile.not_important_count
        + 0.8 * min(profile.quick_close_count, 6)
        + 2.2 * profile.mute_count
    )
    total = max(1.0, positive + negative)
    raw = (positive - negative) / total
    return max(-1.0, min(1.0, raw))


def thread_affinity(profile: Optional[ThreadProfile]) -> float:
    if not profile:
        return 0.0
    _normalize_profile_counts(profile)
    positive = (
        1.3 * profile.important_count
        + 1.3 * profile.reply_count
        + 0.2 * min(profile.open_count, 6)
        + 0.6 * profile.remind_count
    )
    negative = (
        1.1 * profile.not_important_count
        + 0.9 * min(profile.quick_close_count, 6)
        + 1.5 * profile.mute_count
    )
    total = max(1.0, positive + negative)
    raw = (positive - negative) / total
    return max(-1.0, min(1.0, raw))


def _normalize_profile_counts(profile: object) -> None:
    for field in PROFILE_COUNT_FIELDS:
        if getattr(profile, field, None) is None:
            setattr(profile, field, 0)


def _apply_event_to_sender_profile(profile: SenderProfile, event_type: str, when: datetime) -> None:
    _normalize_profile_counts(profile)
    if event_type == "open":
        profile.open_count += 1
    elif event_type == "quick_close":
        profile.quick_close_count += 1
    elif event_type == "reply":
        profile.reply_count += 1
    elif event_type == "important":
        profile.important_count += 1
    elif event_type == "not_important":
        profile.not_important_count += 1
    elif event_type == "mute_sender":
        profile.mute_count += 1
    elif event_type == "remind_sender":
        profile.remind_count += 1
    profile.last_interaction_at = when


def _apply_event_to_thread_profile(profile: ThreadProfile, event_type: str, when: datetime) -> None:
    _normalize_profile_counts(profile)
    if event_type == "open":
        profile.open_count += 1
    elif event_type == "quick_close":
        profile.quick_close_count += 1
    elif event_type == "reply":
        profile.reply_count += 1
    elif event_type == "important":
        profile.important_count += 1
    elif event_type == "not_important":
        profile.not_important_count += 1
    elif event_type == "mute_sender":
        profile.mute_count += 1
    elif event_type == "remind_sender":
        profile.remind_count += 1
    profile.last_interaction_at = when


def record_interaction(
    db: Session,
    user: User,
    email: Email,
    event_type: str,
    when: Optional[datetime] = None,
) -> None:
    when = when or datetime.utcnow()
    sender_key = (email.sender or "").strip().lower()
    if sender_key:
        sender_profile = (
            db.query(SenderProfile)
            .filter(SenderProfile.user_id == user.id, SenderProfile.sender == sender_key)
            .first()
        )
        if not sender_profile:
            sender_profile = SenderProfile(user_id=user.id, sender=sender_key)
            db.add(sender_profile)
            db.flush()
        _apply_event_to_sender_profile(sender_profile, event_type, when)

    thread_key = (email.thread_id or "").strip()
    if thread_key:
        thread_profile = (
            db.query(ThreadProfile)
            .filter(ThreadProfile.user_id == user.id, ThreadProfile.thread_id == thread_key)
            .first()
        )
        if not thread_profile:
            thread_profile = ThreadProfile(user_id=user.id, thread_id=thread_key)
            db.add(thread_profile)
            db.flush()
        _apply_event_to_thread_profile(thread_profile, event_type, when)


def ensure_profiles_backfilled(db: Session, user: User) -> None:
    sender_exists = db.query(SenderProfile.id).filter(SenderProfile.user_id == user.id).first()
    thread_exists = db.query(ThreadProfile.id).filter(ThreadProfile.user_id == user.id).first()
    event_exists = db.query(InteractionEvent.id).filter(InteractionEvent.user_id == user.id).first()
    if sender_exists or thread_exists or not event_exists:
        return

    sender_rows: dict[str, SenderProfile] = {}
    thread_rows: dict[str, ThreadProfile] = {}
    rows = (
        db.query(InteractionEvent, Email)
        .join(Email, InteractionEvent.email_id == Email.id)
        .filter(InteractionEvent.user_id == user.id)
        .order_by(InteractionEvent.created_at.asc(), InteractionEvent.id.asc())
        .all()
    )
    for event, email in rows:
        sender_key = (email.sender or "").strip().lower()
        if sender_key:
            sender_profile = sender_rows.get(sender_key)
            if not sender_profile:
                sender_profile = SenderProfile(user_id=user.id, sender=sender_key)
                sender_rows[sender_key] = sender_profile
            _apply_event_to_sender_profile(sender_profile, event.event_type, event.created_at)

        thread_key = (email.thread_id or "").strip()
        if thread_key:
            thread_profile = thread_rows.get(thread_key)
            if not thread_profile:
                thread_profile = ThreadProfile(user_id=user.id, thread_id=thread_key)
                thread_rows[thread_key] = thread_profile
            _apply_event_to_thread_profile(thread_profile, event.event_type, event.created_at)

    for row in sender_rows.values():
        db.add(row)
    for row in thread_rows.values():
        db.add(row)
    try:
        db.flush()
    except IntegrityError:
        # Another request may have backfilled profiles concurrently.
        # Roll back this partial insert attempt and proceed with existing rows.
        db.rollback()


def feature_weight_items(preference: Optional[UserPreference]) -> list[dict[str, object]]:
    weights = get_feature_weights(preference)
    return [
        {
            "key": item["key"],
            "label": item["label"],
            "description": item["description"],
            "value": round(float(weights[item["key"]]), 4),
        }
        for item in FEATURE_WEIGHT_METADATA
    ]


def interaction_summary(db: Session, user: User) -> dict[str, int]:
    counts = defaultdict(int)
    for (event_type,) in db.query(InteractionEvent.event_type).filter(InteractionEvent.user_id == user.id):
        counts["total_events"] += 1
        if event_type == "open":
            counts["open_count"] += 1
        elif event_type == "quick_close":
            counts["quick_close_count"] += 1
        elif event_type == "reply":
            counts["reply_count"] += 1
        elif event_type == "important":
            counts["important_feedback_count"] += 1
        elif event_type == "not_important":
            counts["not_important_feedback_count"] += 1
        elif event_type == "mute_sender":
            counts["mute_count"] += 1
        elif event_type == "remind_sender":
            counts["remind_count"] += 1
    return dict(counts)


def recent_learning_events(db: Session, user: User, limit: int = 12) -> list[dict[str, object]]:
    rows = (
        db.query(InteractionEvent, Email)
        .join(Email, InteractionEvent.email_id == Email.id)
        .filter(InteractionEvent.user_id == user.id)
        .order_by(InteractionEvent.created_at.desc(), InteractionEvent.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "email_id": email.id,
            "email_subject": email.subject,
            "sender": email.sender,
            "event_type": event.event_type,
            "label": interaction_event_label(event.event_type),
            "detail": interaction_event_detail(event.event_type, event.dwell_ms),
            "origin": interaction_event_origin(event.event_type),
            "impact": interaction_event_impact(event.event_type),
            "created_at": event.created_at,
        }
        for event, email in rows
    ]


def build_user_model_snapshot(db: Session, user: User, preference: UserPreference) -> dict[str, object]:
    ensure_profiles_backfilled(db, user)
    important = important_senders(preference)
    muted = muted_senders(preference)

    sender_profiles = db.query(SenderProfile).filter(SenderProfile.user_id == user.id).all()
    sender_profiles_sorted = sorted(
        sender_profiles,
        key=lambda profile: (abs(sender_affinity(profile)), profile.last_interaction_at or datetime.min),
        reverse=True,
    )[:8]

    thread_profiles = db.query(ThreadProfile).filter(ThreadProfile.user_id == user.id).all()
    thread_profiles_sorted = sorted(
        thread_profiles,
        key=lambda profile: (abs(thread_affinity(profile)), profile.last_interaction_at or datetime.min),
        reverse=True,
    )[:6]

    subject_hints: dict[str, str] = {}
    if thread_profiles_sorted:
        thread_ids = [profile.thread_id for profile in thread_profiles_sorted]
        emails = (
            db.query(Email)
            .filter(Email.user_id == user.id, Email.thread_id.in_(thread_ids))
            .order_by(Email.received_at.desc(), Email.id.desc())
            .all()
        )
        for email in emails:
            if email.thread_id not in subject_hints:
                subject_hints[email.thread_id] = email.subject

    summary = interaction_summary(db, user)
    notes = [
        "The model blends explicit controls with implicit interaction signals.",
        "Sender and thread affinities are learned from opens, replies, quick closes, and feedback.",
        "Feature weights can be edited so the ranking logic stays inspectable and adjustable.",
    ]

    return {
        "email": user.email,
        "important_senders": important,
        "muted_senders": muted,
        "feature_weights": feature_weight_items(preference),
        "sender_profiles": [
            {
                "sender": profile.sender,
                "explicit_state": (
                    "important" if profile.sender in important else "muted" if profile.sender in muted else "neutral"
                ),
                "learned_affinity": round(sender_affinity(profile), 4),
                "open_count": profile.open_count,
                "quick_close_count": profile.quick_close_count,
                "reply_count": profile.reply_count,
                "important_count": profile.important_count,
                "not_important_count": profile.not_important_count,
                "mute_count": profile.mute_count,
                "remind_count": profile.remind_count,
                "last_interaction_at": profile.last_interaction_at,
            }
            for profile in sender_profiles_sorted
        ],
        "thread_profiles": [
            {
                "thread_id": profile.thread_id,
                "subject_hint": subject_hints.get(profile.thread_id, ""),
                "learned_affinity": round(thread_affinity(profile), 4),
                "open_count": profile.open_count,
                "quick_close_count": profile.quick_close_count,
                "reply_count": profile.reply_count,
                "important_count": profile.important_count,
                "not_important_count": profile.not_important_count,
                "mute_count": profile.mute_count,
                "remind_count": profile.remind_count,
                "last_interaction_at": profile.last_interaction_at,
            }
            for profile in thread_profiles_sorted
        ],
        "interaction_summary": {
            "total_events": summary.get("total_events", 0),
            "open_count": summary.get("open_count", 0),
            "quick_close_count": summary.get("quick_close_count", 0),
            "reply_count": summary.get("reply_count", 0),
            "important_feedback_count": summary.get("important_feedback_count", 0),
            "not_important_feedback_count": summary.get("not_important_feedback_count", 0),
            "mute_count": summary.get("mute_count", 0),
            "remind_count": summary.get("remind_count", 0),
        },
        "scrutability_notes": notes,
        "recent_learning_events": recent_learning_events(db, user),
    }
