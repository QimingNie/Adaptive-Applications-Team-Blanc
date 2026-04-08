from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Bucket = Literal["now", "read", "skim", "later"]
FeedbackType = Literal["important", "not_important", "mute_sender", "remind_sender"]
ViewMode = Literal["busy", "normal"]
SignalOrigin = Literal["manual", "observed"]
SignalImpact = Literal["positive", "negative", "neutral"]


class EmailBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: str = ""
    sender: str
    subject: str
    snippet: str
    has_attachment: bool
    is_cc: bool
    received_at: datetime
    score: float
    bucket: Bucket
    needs_action: bool


class ScoreBreakdownItem(BaseModel):
    label: str
    value: float
    detail: str = ""
    source: str


class PersonalizationSignalItem(BaseModel):
    label: str
    detail: str = ""
    origin: SignalOrigin
    impact: SignalImpact


class LearningEventResponse(BaseModel):
    email_id: int
    email_subject: str
    sender: str
    event_type: str
    label: str
    detail: str = ""
    origin: SignalOrigin
    impact: SignalImpact
    created_at: datetime


class EmailListItem(EmailBase):
    reason_summary: str = ""


class EmailDetail(EmailBase):
    body: str = ""
    busy_summary: str = ""
    action_items: str = ""
    reason_summary: str = ""
    model_summary: str = ""
    score_breakdown: list["ScoreBreakdownItem"] = Field(default_factory=list)
    manual_signals: list["PersonalizationSignalItem"] = Field(default_factory=list)
    observed_signals: list["PersonalizationSignalItem"] = Field(default_factory=list)


class ThreadMessageItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender: str
    subject: str
    snippet: str
    received_at: datetime


class ThreadContextResponse(BaseModel):
    thread_id: str
    current_email_id: int
    messages: list[ThreadMessageItem]


class InboxResponse(BaseModel):
    bucket: Bucket
    items: list[EmailListItem]


class FeedbackRequest(BaseModel):
    feedback_type: FeedbackType


class EventRequest(BaseModel):
    email_id: int
    event_type: str
    dwell_ms: int = 0


class SyncRequest(BaseModel):
    seed_count: int = Field(default=20, ge=1, le=200)
    trim_to_count: bool = False


class MessageResponse(BaseModel):
    message: str


class AuthStartResponse(BaseModel):
    auth_url: str


class AuthStatusResponse(BaseModel):
    connected: bool
    email: Optional[str] = None
    can_send: bool = False


class SendEmailRequest(BaseModel):
    to: str = Field(min_length=1)
    cc: str = ""
    subject: str = ""
    body: str = ""
    reply_to_email_id: Optional[int] = None


class FeatureWeightItem(BaseModel):
    key: str
    label: str
    description: str
    value: float


class SenderProfileResponse(BaseModel):
    sender: str
    explicit_state: str
    learned_affinity: float
    open_count: int
    quick_close_count: int
    reply_count: int
    important_count: int
    not_important_count: int
    mute_count: int
    remind_count: int
    last_interaction_at: Optional[datetime] = None


class ThreadProfileResponse(BaseModel):
    thread_id: str
    subject_hint: str = ""
    learned_affinity: float
    open_count: int
    quick_close_count: int
    reply_count: int
    important_count: int
    not_important_count: int
    mute_count: int
    remind_count: int
    last_interaction_at: Optional[datetime] = None


class InteractionSummaryResponse(BaseModel):
    total_events: int = 0
    open_count: int = 0
    quick_close_count: int = 0
    reply_count: int = 0
    important_feedback_count: int = 0
    not_important_feedback_count: int = 0
    mute_count: int = 0
    remind_count: int = 0


class UserModelResponse(BaseModel):
    email: str
    important_senders: list[str] = Field(default_factory=list)
    muted_senders: list[str] = Field(default_factory=list)
    feature_weights: list[FeatureWeightItem] = Field(default_factory=list)
    sender_profiles: list[SenderProfileResponse] = Field(default_factory=list)
    thread_profiles: list[ThreadProfileResponse] = Field(default_factory=list)
    interaction_summary: InteractionSummaryResponse = Field(default_factory=InteractionSummaryResponse)
    scrutability_notes: list[str] = Field(default_factory=list)
    recent_learning_events: list[LearningEventResponse] = Field(default_factory=list)


class UserModelUpdateRequest(BaseModel):
    important_senders: list[str] = Field(default_factory=list)
    muted_senders: list[str] = Field(default_factory=list)
    feature_weights: dict[str, float] = Field(default_factory=dict)


class AuthConfigResponse(BaseModel):
    google_client_id_configured: bool
    google_client_secret_configured: bool
    google_redirect_uri: str
