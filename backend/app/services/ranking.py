# from dataclasses import dataclass
# from datetime import datetime
# from typing import Optional

# from app.models import Email, SenderProfile, ThreadProfile, UserPreference
# from app.services.user_model import (
#     get_feature_weights,
#     important_senders,
#     muted_senders,
#     sender_affinity,
#     thread_affinity,
# )

# ACTION_HINTS = ["deadline", "confirm", "urgent", "action required", "please review", "due", "by noon"]
# QUESTION_HINTS = ["can you", "could you", "would you", "?", "what do you think"]
# REPLY_HINTS = ["reply", "respond", "let me know", "confirm", "send me", "follow up"]


# @dataclass
# class ScoreContribution:
#     label: str
#     value: float
#     detail: str
#     source: str


# @dataclass
# class ScoreResult:
#     score: float
#     bucket: str
#     needs_action: bool
#     breakdown: list[ScoreContribution]


# def _split_csv(raw: str) -> set[str]:
#     return {v.strip().lower() for v in raw.split(",") if v.strip()}


# def clamp_score(score: float) -> float:
#     return max(0.0, min(1.0, score))


# def bucket_for_score(score: float) -> str:
#     if score >= 0.75:
#         return "now"
#     if score >= 0.5:
#         return "read"
#     if score >= 0.3:
#         return "skim"
#     return "later"


# def score_email(
#     email: Email,
#     preference: Optional[UserPreference],
#     sender_profile: Optional[SenderProfile] = None,
#     thread_profile: Optional[ThreadProfile] = None,
# ) -> tuple[float, str, bool]:
#     result = score_email_explained(email, preference, sender_profile, thread_profile)
#     return result.score, result.bucket, result.needs_action


# def score_email_explained(
#     email: Email,
#     preference: Optional[UserPreference],
#     sender_profile: Optional[SenderProfile] = None,
#     thread_profile: Optional[ThreadProfile] = None,
#     now: Optional[datetime] = None,
# ) -> ScoreResult:
#     now = now or datetime.utcnow()
#     weights = get_feature_weights(preference)
#     sender_l = email.sender.lower()
#     text = f"{email.subject} {email.snippet} {email.body}".lower()
#     needs_action = any(h in text for h in ACTION_HINTS)
#     has_question_signal = any(h in text for h in QUESTION_HINTS)
#     has_reply_signal = any(h in text for h in REPLY_HINTS)
#     score = 0.1
#     breakdown = [
#         ScoreContribution(
#             label="Base score",
#             value=0.10,
#             detail="All emails start from the same baseline before adaptation.",
#             source="baseline",
#         )
#     ]

#     important = set(important_senders(preference))
#     muted = set(muted_senders(preference))
#     if sender_l in muted:
#         penalty = -weights["muted_sender_penalty"]
#         score += penalty
#         breakdown.append(
#             ScoreContribution(
#                 label="Muted sender",
#                 value=penalty,
#                 detail="This sender is explicitly muted in the user model.",
#                 source="explicit",
#             )
#         )
#     if sender_l in important:
#         bonus = weights["important_sender_bonus"]
#         score += bonus
#         breakdown.append(
#             ScoreContribution(
#                 label="Important sender",
#                 value=bonus,
#                 detail="This sender is explicitly marked as important.",
#                 source="explicit",
#             )
#         )

#     if not email.is_cc:
#         bonus = weights["direct_bonus"]
#         score += bonus
#         breakdown.append(
#             ScoreContribution(
#                 label="Direct email",
#                 value=bonus,
#                 detail="Direct messages are generally treated as more relevant than CCs.",
#                 source="content",
#             )
#         )
#     if email.has_attachment:
#         bonus = weights["attachment_bonus"]
#         score += bonus
#         breakdown.append(
#             ScoreContribution(
#                 label="Attachment included",
#                 value=bonus,
#                 detail="Attachments often indicate work artefacts or supporting material.",
#                 source="content",
#             )
#         )
#     if needs_action:
#         bonus = weights["action_keyword_bonus"]
#         score += bonus
#         breakdown.append(
#             ScoreContribution(
#                 label="Action language",
#                 value=bonus,
#                 detail="The subject or preview contains deadline or action-oriented language.",
#                 source="content",
#             )
#         )
#     if has_question_signal:
#         bonus = weights["question_bonus"]
#         score += bonus
#         breakdown.append(
#             ScoreContribution(
#                 label="Question signal",
#                 value=bonus,
#                 detail="Questions are often a strong indicator that a response is needed.",
#                 source="content",
#             )
#         )
#     if has_reply_signal:
#         bonus = weights["reply_signal_bonus"]
#         score += bonus
#         breakdown.append(
#             ScoreContribution(
#                 label="Reply signal",
#                 value=bonus,
#                 detail="The wording suggests that a reply or confirmation is expected.",
#                 source="content",
#             )
#         )

#     age_hours = max(0.0, (now - email.received_at).total_seconds() / 3600)
#     if age_hours < 72:
#         recency_factor = max(0.0, 1.0 - (age_hours / 72.0))
#         bonus = weights["recency_bonus"] * recency_factor
#         if bonus > 0:
#             score += bonus
#             breakdown.append(
#                 ScoreContribution(
#                     label="Fresh email",
#                     value=bonus,
#                     detail="Newer emails get a gentle boost so fresh work stays visible.",
#                     source="context",
#                 )
#             )

#     if email.word_count > 350:
#         penalty_scale = min(1.5, email.word_count / 350)
#         penalty = -weights["long_email_penalty"] * penalty_scale
#         score += penalty
#         breakdown.append(
#             ScoreContribution(
#                 label="Long message",
#                 value=penalty,
#                 detail="Long emails are penalized because they take more effort to process quickly.",
#                 source="content",
#             )
#         )

#     sender_score = weights["sender_affinity_scale"] * sender_affinity(sender_profile)
#     if abs(sender_score) > 0.01:
#         score += sender_score
#         breakdown.append(
#             ScoreContribution(
#                 label="Learned sender affinity",
#                 value=sender_score,
#                 detail="Past opens, replies, and feedback for this sender adjust the ranking.",
#                 source="implicit",
#             )
#         )

#     thread_score = weights["thread_affinity_scale"] * thread_affinity(thread_profile)
#     if abs(thread_score) > 0.01:
#         score += thread_score
#         breakdown.append(
#             ScoreContribution(
#                 label="Learned thread affinity",
#                 value=thread_score,
#                 detail="Past interactions with this thread adjust how prominently it is shown.",
#                 source="implicit",
#             )
#         )

#     score = clamp_score(score)
#     return ScoreResult(score=score, bucket=bucket_for_score(score), needs_action=needs_action, breakdown=breakdown)
"""
ranking.py  –  Adaptive inbox ranking for Smart Inbox (Team Blanc)

Exports consumed by adaptation.py:
    ScoreContribution      – dataclass with fields: label, value, detail, source
    ScoreResult            – dataclass with fields: score, bucket, needs_action, breakdown
    bucket_for_score(score)            -> str
    clamp_score(score)                 -> float
    score_email_explained(email, preference, sender_profile, thread_profile) -> ScoreResult

Exports consumed by sync.py / gmail_sync.py:
    score_email(email, preference, sender_profile, thread_profile) -> float
    bucket_for_score(score)                                        -> str
    RE_ACTION                                                      (regex)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

RE_URGENT  = re.compile(r"\b(urgent|asap|immediately|deadline|critical|action required|due)\b", re.I)
RE_SOCIAL  = re.compile(r"\b(unsubscribe|newsletter|promo|offer|deal|sale|discount|opt.?out)\b", re.I)
RE_MEETING = re.compile(r"\b(invite|calendar|meeting|call|zoom|teams|agenda|schedule)\b", re.I)
RE_ACTION  = re.compile(
    r"\b(please|could you|can you|review|approve|confirm|reply|respond|sign|update|let me know|follow up|deadline|action required|due)\b",
    re.I,
)

# ---------------------------------------------------------------------------
# Default feature weight vector
# These map to the keys used by get_feature_weights() in user_model.py.
# adaptation.py reads weights via get_feature_weights(preference) and accesses
# them by key name, so we keep the same key names here for consistency.
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, float] = {
    "direct_bonus":            2.0,
    "action_keyword_bonus":    1.8,
    "question_bonus":          1.2,
    "reply_signal_bonus":      1.0,
    "sender_affinity_scale":   3.0,
    "thread_affinity_scale":   0.8,
    "attachment_bonus":        0.6,
    "recency_bonus":           1.5,
    "long_email_penalty":      0.4,
    "muted_sender_penalty":    5.0,
    "important_sender_bonus":  3.5,
    "opened_bonus":            0.3,
    "quick_close_penalty":     0.3,
    "reply_bonus":             0.8,
}

# ---------------------------------------------------------------------------
# Score range + bucket thresholds
# ---------------------------------------------------------------------------

SCORE_MIN = -15.0
SCORE_MAX =  15.0

BUCKET_NOW  = 4.0
BUCKET_READ = 1.5
BUCKET_SKIM = 0.0


# ---------------------------------------------------------------------------
# ScoreContribution
# Fields match the original (label, value, detail, source) that adaptation.py
# reads. Extra fields (feature, weight, contribution) default to empty/zero
# so existing code that doesn't use them is unaffected.
# ---------------------------------------------------------------------------

@dataclass
class ScoreContribution:
    label:  str
    value:  float
    detail: str
    source: str          # "baseline" | "explicit" | "content" | "context" | "implicit" | "behavior"
    feature:      str   = ""
    weight:       float = 0.0
    contribution: float = 0.0

    def as_dict(self) -> dict:
        return {
            "label":        self.label,
            "value":        round(self.value, 4),
            "detail":       self.detail,
            "source":       self.source,
        }


# ---------------------------------------------------------------------------
# ScoreResult  – returned by score_email_explained, consumed by adaptation.py
# ---------------------------------------------------------------------------

@dataclass
class ScoreResult:
    score:        float
    bucket:       str
    needs_action: bool
    breakdown:    list[ScoreContribution]


# ---------------------------------------------------------------------------
# bucket_for_score  – imported by adaptation.py
# ---------------------------------------------------------------------------

def bucket_for_score(score: float) -> str:
    if score >= BUCKET_NOW:
        return "now"
    if score >= BUCKET_READ:
        return "read"
    if score >= BUCKET_SKIM:
        return "skim"
    return "later"


assign_bucket = bucket_for_score   # backwards-compatible alias


# ---------------------------------------------------------------------------
# clamp_score  – imported by adaptation.py
# ---------------------------------------------------------------------------

def clamp_score(score: float) -> float:
    return max(SCORE_MIN, min(SCORE_MAX, score))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_weights(preference: Any) -> dict[str, float]:
    """
    Load feature weights from UserPreference.feature_weights_json.
    Falls back to DEFAULT_WEIGHTS if nothing stored yet.
    """
    raw = getattr(preference, "feature_weights_json", None)
    if raw:
        try:
            w = json.loads(raw)
            if isinstance(w, dict):
                # Fill in any missing keys with defaults
                merged = dict(DEFAULT_WEIGHTS)
                merged.update({k: float(v) for k, v in w.items() if k in DEFAULT_WEIGHTS})
                return merged
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    return dict(DEFAULT_WEIGHTS)


def _sender_lists(preference: Any) -> tuple[set[str], set[str]]:
    muted = {
        s.strip().lower()
        for s in (getattr(preference, "muted_senders", None) or "").split(",")
        if s.strip()
    }
    important = {
        s.strip().lower()
        for s in (getattr(preference, "important_senders", None) or "").split(",")
        if s.strip()
    }
    return muted, important


# ---------------------------------------------------------------------------
# score_email_explained  – imported by adaptation.py
#
# Returns a ScoreResult (NOT a tuple) so adaptation.py can do:
#   base_result.score
#   base_result.breakdown
#   base_result.needs_action
# ---------------------------------------------------------------------------

def score_email_explained(
    email: Any,
    preference: Any,
    sender_profile: Any = None,
    thread_profile: Any = None,
    now: Optional[datetime] = None,
) -> ScoreResult:
    """
    Score an email and return a ScoreResult with full breakdown.

    Parameters
    ----------
    email          : Email ORM object
    preference     : UserPreference ORM object (or None)
    sender_profile : SenderProfile ORM object (or None)
    thread_profile : ThreadProfile ORM object (or None)
    now            : override current time (useful in tests)
    """
    now = now or datetime.now(timezone.utc)
    weights = _load_weights(preference)
    muted, important = _sender_lists(preference) if preference else (set(), set())

    sender_l = (getattr(email, "sender", "") or "").lower()
    subject  = getattr(email, "subject", "") or ""
    snippet  = getattr(email, "snippet", "") or ""
    body     = getattr(email, "body",    "") or ""
    text     = f"{subject} {snippet} {body}".lower()

    needs_action = bool(RE_ACTION.search(text))

    score: float = 0.1
    breakdown: list[ScoreContribution] = [
        ScoreContribution(
            label="Base score",
            value=0.1,
            detail="All emails start from the same baseline before adaptation.",
            source="baseline",
        )
    ]

    # ---- explicit: muted / important ----------------------------------------

    if sender_l in muted or (sender_profile and sender_profile.mute_count > 0):
        penalty = -weights["muted_sender_penalty"]
        score += penalty
        breakdown.append(ScoreContribution(
            label="Muted sender",
            value=penalty,
            detail="This sender is explicitly muted in the user model.",
            source="explicit",
        ))

    if sender_l in important or (sender_profile and sender_profile.important_count > 0):
        bonus = weights["important_sender_bonus"]
        score += bonus
        breakdown.append(ScoreContribution(
            label="Important sender",
            value=bonus,
            detail="This sender is explicitly marked as important.",
            source="explicit",
        ))

    # ---- content signals ----------------------------------------------------

    if not getattr(email, "is_cc", False):
        bonus = weights["direct_bonus"]
        score += bonus
        breakdown.append(ScoreContribution(
            label="Direct email",
            value=bonus,
            detail="Direct messages are generally more relevant than CCs.",
            source="content",
        ))

    if getattr(email, "has_attachment", False):
        bonus = weights["attachment_bonus"]
        score += bonus
        breakdown.append(ScoreContribution(
            label="Attachment included",
            value=bonus,
            detail="Attachments often indicate work artefacts or supporting material.",
            source="content",
        ))

    if needs_action:
        bonus = weights["action_keyword_bonus"]
        score += bonus
        breakdown.append(ScoreContribution(
            label="Action language",
            value=bonus,
            detail="The subject or body contains deadline or action-oriented language.",
            source="content",
        ))

    if re.search(r"\b(can you|could you|what do you think|\?)\b", text, re.I):
        bonus = weights["question_bonus"]
        score += bonus
        breakdown.append(ScoreContribution(
            label="Question signal",
            value=bonus,
            detail="Questions are a strong indicator that a response is needed.",
            source="content",
        ))

    if re.search(r"\b(reply|respond|let me know|confirm|send me|follow up)\b", text, re.I):
        bonus = weights["reply_signal_bonus"]
        score += bonus
        breakdown.append(ScoreContribution(
            label="Reply signal",
            value=bonus,
            detail="The wording suggests a reply or confirmation is expected.",
            source="content",
        ))

    word_count = getattr(email, "word_count", 0) or (len(body) // 5)
    if word_count > 350:
        penalty_scale = min(1.5, word_count / 350)
        penalty = -weights["long_email_penalty"] * penalty_scale
        score += penalty
        breakdown.append(ScoreContribution(
            label="Long message",
            value=round(penalty, 3),
            detail="Long emails are penalised because they take more effort to process quickly.",
            source="content",
        ))

    # ---- recency ------------------------------------------------------------

    received_at = getattr(email, "received_at", None)
    if isinstance(received_at, datetime):
        ra = received_at if received_at.tzinfo else received_at.replace(tzinfo=timezone.utc)
        age_hours = max(0.0, (now - ra).total_seconds() / 3600)
    else:
        age_hours = 0.0

    if age_hours < 72:
        recency_factor = max(0.0, 1.0 - (age_hours / 72.0))
        bonus = weights["recency_bonus"] * recency_factor
        if bonus > 0.01:
            score += bonus
            breakdown.append(ScoreContribution(
                label="Fresh email",
                value=round(bonus, 3),
                detail="Newer emails get a gentle boost so fresh work stays visible.",
                source="context",
            ))

    # ---- implicit: sender affinity ------------------------------------------

    if sender_profile:
        total = max(
            sender_profile.open_count
            + sender_profile.reply_count
            + sender_profile.quick_close_count,
            1,
        )
        open_rate  = sender_profile.open_count         / total
        reply_rate = sender_profile.reply_count        / total
        skip_rate  = sender_profile.quick_close_count  / total

        # Net affinity: (opens + replies - skips) normalised to [-1, 1]
        affinity = max(-1.0, min(1.0, open_rate + reply_rate - skip_rate))
        sender_score = weights["sender_affinity_scale"] * affinity
        if abs(sender_score) > 0.01:
            score += sender_score
            breakdown.append(ScoreContribution(
                label="Learned sender affinity",
                value=round(sender_score, 3),
                detail="Past opens, replies, and quick-closes for this sender adjust the ranking.",
                source="implicit",
            ))

    # ---- implicit: thread affinity ------------------------------------------

    if thread_profile:
        total_t = max(thread_profile.open_count + thread_profile.reply_count, 1)
        t_affinity = min(
            1.0,
            (thread_profile.open_count + thread_profile.reply_count) / total_t,
        )
        thread_score = weights["thread_affinity_scale"] * t_affinity
        if abs(thread_score) > 0.01:
            score += thread_score
            breakdown.append(ScoreContribution(
                label="Learned thread affinity",
                value=round(thread_score, 3),
                detail="Past interactions with this thread adjust how prominently it is shown.",
                source="implicit",
            ))

    score = clamp_score(score)
    breakdown.sort(key=lambda c: abs(c.value), reverse=True)

    return ScoreResult(
        score=score,
        bucket=bucket_for_score(score),
        needs_action=needs_action,
        breakdown=breakdown,
    )


# ---------------------------------------------------------------------------
# score_email  – used by sync.py and gmail_sync.py
# Returns just the float score.
# ---------------------------------------------------------------------------

def score_email(
    email: Any,
    preference: Any,
    sender_profile: Any = None,
    thread_profile: Any = None,
) -> float:
    return score_email_explained(email, preference, sender_profile, thread_profile).score


# ---------------------------------------------------------------------------
# rank_emails  – bulk helper
# ---------------------------------------------------------------------------

def rank_emails(
    emails: list[Any],
    preference: Any,
    sender_profiles: Optional[dict[str, Any]] = None,
    thread_profiles: Optional[dict[str, Any]] = None,
) -> list[tuple[Any, float, str]]:
    """
    Score and bucket a list of emails, sorted by score descending.
    """
    sender_profiles = sender_profiles or {}
    thread_profiles = thread_profiles or {}
    results = []
    for email in emails:
        sp = sender_profiles.get(getattr(email, "sender", ""), None)
        tp = thread_profiles.get(getattr(email, "thread_id", ""), None)
        s  = score_email(email, preference, sp, tp)
        b  = bucket_for_score(s)
        results.append((email, s, b))
    results.sort(key=lambda x: x[1], reverse=True)
    return results


# ---------------------------------------------------------------------------
# update_weights_from_feedback
# Performs one SGD step and returns the updated weights dict as JSON string,
# ready to be saved back to preference.feature_weights_json.
# ---------------------------------------------------------------------------

REWARD_MAP: dict[str, float] = {
    "important":     +1.5,
    "not_important": -1.0,
    "mute_sender":   -3.0,
    "remind_sender": +0.5,
    "open":          +0.3,
    "reply":         +0.8,
    "quick_close":   -0.3,
    "skip":          -0.4,
    "delete":        -0.6,
    "archive":       -0.2,
}


def update_weights_from_feedback(
    email: Any,
    action: str,
    preference: Any,
    sender_profile: Any = None,
    thread_profile: Any = None,
) -> str:
    """
    Perform one online SGD step.
    Returns updated weights as a JSON string to store in
    preference.feature_weights_json.
    """
    reward = REWARD_MAP.get(action, 0.0)
    if reward == 0.0:
        return json.dumps(_load_weights(preference))

    weights = _load_weights(preference)
    result  = score_email_explained(email, preference, sender_profile, thread_profile)

    total_updates = getattr(preference, "total_updates", 0) or 0
    lr = 0.15 / (1.0 + 0.001 * total_updates)

    # Map contribution labels back to weight keys
    label_to_key = {
        "Direct email":               "direct_bonus",
        "Action language":            "action_keyword_bonus",
        "Question signal":            "question_bonus",
        "Reply signal":               "reply_signal_bonus",
        "Learned sender affinity":    "sender_affinity_scale",
        "Learned thread affinity":    "thread_affinity_scale",
        "Attachment included":        "attachment_bonus",
        "Fresh email":                "recency_bonus",
        "Long message":               "long_email_penalty",
        "Muted sender":               "muted_sender_penalty",
        "Important sender":           "important_sender_bonus",
        "Previously opened":          "opened_bonus",
        "Quick-close history":        "quick_close_penalty",
        "Reply history":              "reply_bonus",
    }

    for contrib in result.breakdown:
        key = label_to_key.get(contrib.label)
        if key and key in weights:
            weights[key] += lr * reward * abs(contrib.value)
            weights[key]  = max(-10.0, min(10.0, weights[key]))

    return json.dumps(weights)