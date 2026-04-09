"""API contracts for Gmail-backed users: sync must populate inbox; normal view must list all mail."""

from datetime import datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Email, OAuthToken, User, UserPreference

USER_EMAIL = "gmailuser@example.com"
HDR = {"X-User-Email": USER_EMAIL}


@pytest.fixture(autouse=True)
def _reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _seed_gmail_user():
    db = SessionLocal()
    user = User(email=USER_EMAIL)
    db.add(user)
    db.flush()
    db.add(UserPreference(user_id=user.id))
    db.add(
        OAuthToken(
            user_id=user.id,
            access_token="fake-access",
            refresh_token="fake-refresh",
            token_type="Bearer",
            scope="https://www.googleapis.com/auth/gmail.readonly",
            expires_at=datetime.utcnow() + timedelta(days=1),
            updated_at=datetime.utcnow(),
        )
    )
    db.commit()
    db.close()


def _fake_sync_gmail(db, user, max_results: int):
    uid = uuid4().hex[:8]
    for i in range(2):
        db.add(
            Email(
                user_id=user.id,
                external_id=f"gmail-{uid}-{i}",
                thread_id=f"t{i}",
                sender=f"sender{i}@example.com",
                subject=f"Subject {i}",
                snippet="snippet",
                body="body text",
                received_at=datetime.utcnow(),
                score=0.2,
                bucket="later",
                needs_action=False,
            )
        )
    db.commit()
    return 2


def _seed_email(sender: str = "alice@example.com", thread_id: str = "thread-1") -> int:
    db = SessionLocal()
    user = db.query(User).filter(User.email == USER_EMAIL).one()
    email = Email(
        user_id=user.id,
        external_id=f"seed-{uuid4().hex[:8]}",
        thread_id=thread_id,
        sender=sender,
        subject="Quarterly review",
        snippet="Please review and confirm the latest draft.",
        body="Please review and confirm the latest draft.",
        received_at=datetime.utcnow(),
        score=0.2,
        bucket="later",
        needs_action=True,
    )
    db.add(email)
    db.commit()
    db.refresh(email)
    email_id = email.id
    db.close()
    return email_id


def test_gmail_sync_then_normal_inbox_lists_all_buckets(client: TestClient):
    _seed_gmail_user()
    with patch("app.api.routes.sync_gmail_inbox", _fake_sync_gmail):
        sync = client.post(
            "/api/sync/run",
            headers=HDR,
            json={"seed_count": 24, "trim_to_count": False},
        )
    assert sync.status_code == 200, sync.text

    read_normal = client.get("/api/inbox?bucket=read&view=normal", headers=HDR)
    later_normal = client.get("/api/inbox?bucket=later&view=normal", headers=HDR)
    assert read_normal.status_code == 200
    assert later_normal.status_code == 200
    a = read_normal.json()["items"]
    b = later_normal.json()["items"]
    assert len(a) == 2 and len(b) == 2
    assert {x["id"] for x in a} == {x["id"] for x in b}


def test_inbox_normal_works_with_user_email_query_only(client: TestClient):
    """Regression: GET requests must resolve the same user if X-User-Email is stripped."""
    _seed_gmail_user()
    with patch("app.api.routes.sync_gmail_inbox", _fake_sync_gmail):
        client.post(
            "/api/sync/run",
            params={"user_email": USER_EMAIL},
            json={"seed_count": 24, "trim_to_count": False},
        )
    inbox = client.get(
        f"/api/inbox?bucket=now&view=normal&user_email={USER_EMAIL}",
    )
    assert inbox.status_code == 200
    assert len(inbox.json()["items"]) == 2


def test_busy_later_filter_still_applies_under_busy_view(client: TestClient):
    _seed_gmail_user()
    with patch("app.api.routes.sync_gmail_inbox", _fake_sync_gmail):
        client.post(
            "/api/sync/run",
            headers=HDR,
            json={"seed_count": 24, "trim_to_count": False},
        )
    busy_now = client.get("/api/inbox?bucket=now&view=busy", headers=HDR).json()["items"]
    busy_later = client.get("/api/inbox?bucket=later&view=busy", headers=HDR).json()["items"]
    assert len(busy_later) == 2
    assert len(busy_now) == 0


def test_personalization_signals_and_learning_feed_are_exposed(client: TestClient):
    _seed_gmail_user()
    email_id = _seed_email()

    open_resp = client.post(
        "/api/events",
        headers=HDR,
        json={"email_id": email_id, "event_type": "open", "dwell_ms": 0},
    )
    quick_close_resp = client.post(
        "/api/events",
        headers=HDR,
        json={"email_id": email_id, "event_type": "quick_close", "dwell_ms": 2400},
    )
    feedback_resp = client.post(
        f"/api/emails/{email_id}/feedback",
        headers=HDR,
        json={"feedback_type": "important"},
    )

    assert open_resp.status_code == 200, open_resp.text
    assert quick_close_resp.status_code == 200, quick_close_resp.text
    assert feedback_resp.status_code == 200, feedback_resp.text

    detail = client.get(f"/api/emails/{email_id}?mode=busy", headers=HDR)
    assert detail.status_code == 200, detail.text
    detail_json = detail.json()

    manual_labels = {item["label"] for item in detail_json["manual_signals"]}
    observed_labels = {item["label"] for item in detail_json["observed_signals"]}

    assert "Sender marked important" in manual_labels
    assert "This email was marked important" in manual_labels
    assert "Opened before" in observed_labels
    assert any(label.startswith("Quick-closed") for label in observed_labels)

    model = client.get("/api/model", headers=HDR)
    assert model.status_code == 200, model.text
    model_json = model.json()
    event_types = {item["event_type"] for item in model_json["recent_learning_events"]}

    assert {"open", "quick_close", "important"}.issubset(event_types)
