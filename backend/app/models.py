from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    gmail_history_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    emails = relationship("Email", back_populates="user")
    preferences = relationship("UserPreference", back_populates="user", uselist=False)
    oauth_token = relationship("OAuthToken", back_populates="user", uselist=False)


class Email(Base):
    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    thread_id: Mapped[str] = mapped_column(String(255), index=True)
    sender: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(String(512))
    snippet: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    has_attachment: Mapped[bool] = mapped_column(Boolean, default=False)
    is_cc: Mapped[bool] = mapped_column(Boolean, default=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    bucket: Mapped[str] = mapped_column(String(20), default="later", index=True)
    busy_summary: Mapped[str] = mapped_column(Text, default="")
    action_items: Mapped[str] = mapped_column(Text, default="")
    needs_action: Mapped[bool] = mapped_column(Boolean, default=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)

    user = relationship("User", back_populates="emails")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True)
    muted_senders: Mapped[str] = mapped_column(Text, default="")
    important_senders: Mapped[str] = mapped_column(Text, default="")
    long_email_penalty: Mapped[float] = mapped_column(Float, default=0.15)
    feature_weights_json: Mapped[str] = mapped_column(Text, default="")

    user = relationship("User", back_populates="preferences")


class SenderProfile(Base):
    __tablename__ = "sender_profiles"
    __table_args__ = (UniqueConstraint("user_id", "sender", name="uq_sender_profiles_user_sender"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    sender: Mapped[str] = mapped_column(String(255), index=True)
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    quick_close_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    important_count: Mapped[int] = mapped_column(Integer, default=0)
    not_important_count: Mapped[int] = mapped_column(Integer, default=0)
    mute_count: Mapped[int] = mapped_column(Integer, default=0)
    remind_count: Mapped[int] = mapped_column(Integer, default=0)
    last_interaction_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)


class ThreadProfile(Base):
    __tablename__ = "thread_profiles"
    __table_args__ = (UniqueConstraint("user_id", "thread_id", name="uq_thread_profiles_user_thread"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    thread_id: Mapped[str] = mapped_column(String(255), index=True)
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    quick_close_count: Mapped[int] = mapped_column(Integer, default=0)
    reply_count: Mapped[int] = mapped_column(Integer, default=0)
    important_count: Mapped[int] = mapped_column(Integer, default=0)
    not_important_count: Mapped[int] = mapped_column(Integer, default=0)
    mute_count: Mapped[int] = mapped_column(Integer, default=0)
    remind_count: Mapped[int] = mapped_column(Integer, default=0)
    last_interaction_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, default=None)


class InteractionEvent(Base):
    __tablename__ = "interaction_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    email_id: Mapped[int] = mapped_column(Integer, ForeignKey("emails.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    dwell_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    state: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, index=True)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str] = mapped_column(Text, default="")
    token_type: Mapped[str] = mapped_column(String(50), default="Bearer")
    scope: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="oauth_token")
