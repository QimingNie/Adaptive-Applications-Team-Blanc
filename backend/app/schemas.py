from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Bucket = Literal["now", "read", "skim", "later"]
FeedbackType = Literal["important", "not_important", "mute_sender", "remind_sender"]
ViewMode = Literal["busy", "normal"]


class EmailBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender: str
    subject: str
    snippet: str
    has_attachment: bool
    is_cc: bool
    received_at: datetime
    score: float
    bucket: Bucket
    needs_action: bool


class EmailListItem(EmailBase):
    pass


class EmailDetail(EmailBase):
    body: str = ""
    busy_summary: str = ""
    action_items: str = ""


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


class AuthConfigResponse(BaseModel):
    google_client_id_configured: bool
    google_client_secret_configured: bool
    google_redirect_uri: str
