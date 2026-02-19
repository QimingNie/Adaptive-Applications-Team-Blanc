from datetime import datetime, timedelta
import random
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Email, User, UserPreference
from app.services.ranking import score_email
from app.services.summary import generate_busy_summary

SEED_SENDERS = [
    "manager@company.com",
    "alerts@service.com",
    "newsletter@weekly.io",
    "teammate@company.com",
    "noreply@platform.com",
]
SEED_SUBJECTS = [
    "Please confirm the delivery timeline",
    "Weekly digest: product updates",
    "Action required: security review",
    "Project thread update",
    "Subscription offer this week",
]


def ensure_demo_user(db: Session) -> User:
    user = db.query(User).filter(User.email == "demo@smartinbox.local").first()
    if user:
        return user

    user = User(email="demo@smartinbox.local")
    db.add(user)
    db.flush()

    pref = UserPreference(
        user_id=user.id,
        muted_senders="newsletter@weekly.io,noreply@platform.com",
        important_senders="manager@company.com,teammate@company.com",
    )
    db.add(pref)
    db.commit()
    db.refresh(user)
    return user


def seed_mock_emails(db: Session, user: User, count: int = 20) -> int:
    preference = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()

    created = 0
    for idx in range(count):
        sender = random.choice(SEED_SENDERS)
        subject = random.choice(SEED_SUBJECTS)
        snippet = f"{subject}. Please review and confirm if needed."
        body = f"{snippet} This is a generated email content for Smart Inbox MVP."
        received_at = datetime.utcnow() - timedelta(minutes=idx * 13)
        mail = Email(
            user_id=user.id,
            external_id=f"mock-{user.id}-{uuid4().hex}",
            thread_id=f"thread-{random.randint(1, 8)}",
            sender=sender,
            subject=subject,
            snippet=snippet,
            body=body,
            has_attachment=random.choice([True, False]),
            is_cc=random.choice([True, False]),
            word_count=len(body.split()),
            received_at=received_at,
        )
        score, bucket, needs_action = score_email(mail, preference)
        summary, action_items = generate_busy_summary(mail)
        mail.score = score
        mail.bucket = bucket
        mail.needs_action = needs_action
        mail.busy_summary = summary
        mail.action_items = action_items

        db.add(mail)
        created += 1

    db.commit()
    return created
