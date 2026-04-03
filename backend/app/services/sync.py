from dataclasses import dataclass
from datetime import datetime, timedelta
import random
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Email, InteractionEvent, User, UserPreference
from app.services.adaptation import rescore_user_emails
from app.services.ranking import score_email
from app.services.summary import generate_busy_summary


@dataclass(frozen=True)
class MockEmailTemplate:
    sender: str
    subject: str
    snippet: str
    body: str
    has_attachment: bool = False
    is_cc: bool = False
    thread_group: str = "general"


@dataclass(frozen=True)
class MockEmailContext:
    label: str
    detail: str
    owner: str
    due_phrase: str
    checkpoint: str


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).strip().lower()


def _email_fingerprint(sender: str, subject: str, body: str) -> tuple[str, str, str]:
    return (
        _normalize_text(sender),
        _normalize_text(subject),
        _normalize_text(body),
    )


def _slugify(value: str) -> str:
    chars = [ch.lower() if ch.isalnum() else "-" for ch in value]
    slug = "".join(chars).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "general"


def _expand_template(base: MockEmailTemplate, context: MockEmailContext) -> MockEmailTemplate:
    context_note = (
        f"Current thread context: {context.detail} "
        f"The working owner is {context.owner}. "
        f"Please respond by {context.due_phrase} so we can stay aligned before {context.checkpoint}."
    )
    return MockEmailTemplate(
        sender=base.sender,
        subject=f"{base.subject}: {context.label}",
        snippet=f"{base.snippet} {context.detail}",
        body=f"{base.body} {context_note}",
        has_attachment=base.has_attachment,
        is_cc=base.is_cc,
        thread_group=f"{base.thread_group}-{_slugify(context.label)}",
    )


BASE_MOCK_EMAIL_TEMPLATES = [
    MockEmailTemplate(
        sender="manager@company.com",
        subject="Please confirm the delivery timeline",
        snippet="We need a yes or no on the pilot schedule before tomorrow's steering call.",
        body=(
            "We need to confirm the delivery timeline for the pilot release before tomorrow's "
            "steering call. The client asked whether we can still ship the revised dashboard by "
            "Thursday afternoon and whether QA will finish before the deadline. Please review "
            "the remaining tasks, flag anything that could move the deadline, and confirm whether "
            "design sign-off is complete. If there is risk, reply with the blocker, owner, and "
            "the soonest realistic date so I can update leadership."
        ),
        has_attachment=True,
        thread_group="delivery",
    ),
    MockEmailTemplate(
        sender="alerts@service.com",
        subject="Action required: security review",
        snippet="Three admin logins were flagged and the access review needs confirmation today.",
        body=(
            "Action required: the weekly security review found three admin logins that do not "
            "match the usual pattern for the finance workspace. Please review the attached access "
            "report, confirm which sessions belong to the team, and remove any permissions that "
            "should not still be active. The security deadline for sign-off is today at 5 PM, "
            "and the audit log will stay open until we confirm the final status."
        ),
        has_attachment=True,
        thread_group="security",
    ),
    MockEmailTemplate(
        sender="teammate@company.com",
        subject="Project thread update",
        snippet="Design approved the new handoff, but we still need review on the rollout checklist.",
        body=(
            "Quick project update: design approved the handoff for the onboarding refresh, and "
            "engineering says the new build is stable in staging. The only open item is the rollout "
            "checklist for customer support, because we still need someone to review the response "
            "macros and confirm who owns weekend monitoring. If you can review the checklist before "
            "tomorrow morning, I will fold the changes into the release notes and send the final "
            "confirmation to support."
        ),
        is_cc=True,
        thread_group="project",
    ),
    MockEmailTemplate(
        sender="newsletter@weekly.io",
        subject="Weekly digest: product updates",
        snippet="This week's digest covers launch metrics, experiment results, and next quarter bets.",
        body=(
            "Here is the weekly product digest covering launch metrics, experiment results, and the "
            "three bets leadership wants to explore next quarter. Activation improved by four percent "
            "after the trial-page copy change, support volume stayed flat, and the referral experiment "
            "showed stronger conversion on mobile than desktop. There is no action required, but the "
            "section on onboarding drop-off is worth a quick read before Friday's planning session."
        ),
        thread_group="digest",
    ),
    MockEmailTemplate(
        sender="noreply@platform.com",
        subject="Subscription offer this week",
        snippet="Your workspace can upgrade storage this week if you want the new retention controls.",
        body=(
            "Your workspace is eligible for a temporary storage upgrade that includes longer retention "
            "controls, audit exports, and faster archive search. The offer runs through the end of the "
            "week and does not require any immediate action, but the plan summary includes pricing and "
            "a side-by-side feature table if you want to review options before renewal. If you are not "
            "the billing owner, feel free to ignore this message."
        ),
        thread_group="marketing",
    ),
    MockEmailTemplate(
        sender="manager@company.com",
        subject="Customer escalation for review",
        snippet="The Northwind account reported delayed exports and wants a recovery plan by noon.",
        body=(
            "The Northwind account escalated delayed exports during their monthly finance close and "
            "they want a recovery plan by noon. Support has already restored the failed jobs, but the "
            "customer wants a short explanation of what happened, what we reviewed, and how we will "
            "prevent it from happening again before next month's close. Please review the incident notes, "
            "confirm whether the root cause summary is accurate, and send me two bullet points I can use "
            "in the customer reply."
        ),
        has_attachment=True,
        thread_group="customer",
    ),
    MockEmailTemplate(
        sender="teammate@company.com",
        subject="Notes from vendor call",
        snippet="The vendor can support the integration, but they need confirmation on the event schema.",
        body=(
            "Sharing notes from today's vendor call. They can support the integration on the current "
            "timeline, but they need us to confirm the event schema and the retry behavior before they "
            "start implementation next week. I wrote up the main decisions, open questions, and the one "
            "dependency they flagged around webhook ordering. Please review the summary and confirm if "
            "you agree with the proposed payload fields so I can send the final answer tomorrow."
        ),
        thread_group="vendor",
    ),
    MockEmailTemplate(
        sender="alerts@service.com",
        subject="Reminder: backup policy review",
        snippet="The backup policy review is due Friday and the current retention window needs approval.",
        body=(
            "Reminder that the backup policy review is due Friday. The proposed update shortens warm "
            "storage retention, keeps monthly snapshots for compliance, and changes who gets paged on "
            "restore failures outside business hours. Please review the policy notes, confirm whether "
            "the retention window matches the legal requirement, and reply if the on-call rotation needs "
            "to change before we lock the document for approval."
        ),
        is_cc=True,
        thread_group="ops",
    ),
]


MOCK_EMAIL_CONTEXTS = [
    MockEmailContext(
        label="Northwind Pilot",
        detail="The customer wants a revised status after the latest dashboard feedback.",
        owner="Maya",
        due_phrase="Thursday at 3 PM",
        checkpoint="Friday's steering call",
    ),
    MockEmailContext(
        label="Atlas Rollout",
        detail="Leadership asked for a firmer handoff plan before the launch freeze.",
        owner="Priya",
        due_phrase="tomorrow morning",
        checkpoint="the launch readiness review",
    ),
    MockEmailContext(
        label="Finance Workspace",
        detail="The finance workspace logs need one more pass before compliance sign-off.",
        owner="Sam",
        due_phrase="today at 5 PM",
        checkpoint="the compliance review",
    ),
    MockEmailContext(
        label="Support Enablement",
        detail="Customer support still needs owner notes and fallback steps for the rollout.",
        owner="Elena",
        due_phrase="Friday noon",
        checkpoint="the enablement handoff",
    ),
    MockEmailContext(
        label="Vendor Integration",
        detail="The partner team is blocked until we confirm the final payload and retry policy.",
        owner="Jordan",
        due_phrase="Wednesday afternoon",
        checkpoint="the vendor implementation kickoff",
    ),
    MockEmailContext(
        label="Q2 Planning",
        detail="Planning notes are open because the metrics summary changed after this week's experiment readout.",
        owner="Alex",
        due_phrase="the end of the week",
        checkpoint="Monday's planning session",
    ),
]


MOCK_EMAIL_TEMPLATES = [
    _expand_template(template, context)
    for template in BASE_MOCK_EMAIL_TEMPLATES
    for context in MOCK_EMAIL_CONTEXTS
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


def _delete_emails_and_events(db: Session, emails: list[Email]) -> int:
    if not emails:
        return 0

    email_ids = [email.id for email in emails]
    db.query(InteractionEvent).filter(InteractionEvent.email_id.in_(email_ids)).delete(
        synchronize_session=False
    )
    for email in emails:
        db.delete(email)
    return len(emails)


def seed_mock_emails(
    db: Session, user: User, count: int = 20, trim_to_count: bool = False
) -> int:
    preference = db.query(UserPreference).filter(UserPreference.user_id == user.id).first()
    existing_emails = (
        db.query(Email)
        .filter(Email.user_id == user.id)
        .order_by(Email.received_at.desc(), Email.id.desc())
        .all()
    )

    unique_emails: list[Email] = []
    duplicate_emails: list[Email] = []
    seen_fingerprints: set[tuple[str, str, str]] = set()
    for existing in existing_emails:
        fingerprint = _email_fingerprint(existing.sender, existing.subject, existing.body or existing.snippet)
        if fingerprint in seen_fingerprints:
            duplicate_emails.append(existing)
            continue
        seen_fingerprints.add(fingerprint)
        unique_emails.append(existing)

    deleted_count = _delete_emails_and_events(db, duplicate_emails)

    target_total = max(1, count)
    emails_to_trim: list[Email] = []
    if trim_to_count and len(unique_emails) > target_total:
        emails_to_trim = unique_emails[target_total:]
        unique_emails = unique_emails[:target_total]
    deleted_count += _delete_emails_and_events(db, emails_to_trim)

    seen_fingerprints = {
        _email_fingerprint(email.sender, email.subject, email.body or email.snippet)
        for email in unique_emails
    }

    available_templates = [
        template
        for template in MOCK_EMAIL_TEMPLATES
        if _email_fingerprint(template.sender, template.subject, template.body) not in seen_fingerprints
    ]
    random.shuffle(available_templates)

    created = 0
    needed = min(len(available_templates), max(0, target_total - len(unique_emails)))
    for idx, template in enumerate(available_templates[:needed]):
        received_at = datetime.utcnow() - timedelta(minutes=idx * 13)
        mail = Email(
            user_id=user.id,
            external_id=f"mock-{user.id}-{uuid4().hex}",
            thread_id=f"{template.thread_group}-{random.randint(1, 4)}",
            sender=template.sender,
            subject=template.subject,
            snippet=template.snippet,
            body=template.body,
            has_attachment=template.has_attachment,
            is_cc=template.is_cc,
            word_count=len(template.body.split()),
            received_at=received_at,
        )
        score, bucket, needs_action = score_email(mail, preference)
        summary, action_items = generate_busy_summary(mail, allow_llm=False)
        mail.score = score
        mail.bucket = bucket
        mail.needs_action = needs_action
        mail.busy_summary = summary
        mail.action_items = action_items

        db.add(mail)
        created += 1

    if created:
        db.flush()
        rescore_user_emails(db, user, preference)
    if deleted_count or created:
        db.commit()
    return created
