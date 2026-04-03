import json
import logging
import re
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.models import Email

logger = logging.getLogger(__name__)


def generate_busy_summary(email: Email, allow_llm: bool = True) -> tuple[str, str]:
    compact = _compact_email_text(email)
    if not compact:
        return "No content available.", ""

    if allow_llm and _llm_enabled(compact):
        llm_result = _generate_llm_summary(email, compact)
        if llm_result:
            return llm_result

    demo_summary = _generate_demo_summary(email)
    if demo_summary:
        return demo_summary

    return _generate_heuristic_summary(compact)


def _compact_email_text(email: Email) -> str:
    parts = [email.subject.strip(), email.body.strip() or email.snippet.strip()]
    joined = "\n".join(part for part in parts if part)
    return " ".join(joined.split())


def summary_needs_refresh(email: Email) -> bool:
    compact = _compact_email_text(email)
    if not compact:
        return not (email.busy_summary or "").strip()

    current_summary = " ".join((email.busy_summary or "").split()).strip()
    current_actions = " ".join((email.action_items or "").split()).strip()
    heuristic_summary, heuristic_actions = _generate_heuristic_summary(compact)

    if not current_summary:
        return True

    if not _llm_enabled(compact):
        return False

    heuristic_summary = " ".join(heuristic_summary.split()).strip()
    heuristic_actions = " ".join(heuristic_actions.split()).strip()
    return current_summary == heuristic_summary and current_actions == heuristic_actions


def _llm_enabled(compact: str) -> bool:
    provider = settings.summary_provider.strip().lower()
    if provider in {"", "off", "none", "false"}:
        return False

    model = settings.summary_model.strip()
    if not model:
        return False

    min_chars = max(0, settings.summary_min_llm_chars)
    if len(compact) < min_chars:
        return False

    if provider == "openai":
        return bool(settings.summary_api_key.strip())

    return provider == "ollama"


def _generate_heuristic_summary(compact: str) -> tuple[str, str]:
    summary = compact[:220] + ("..." if len(compact) > 220 else "")

    action_items = []
    text_l = compact.lower()
    if "deadline" in text_l or "due" in text_l:
        action_items.append("Check the deadline or due date.")
    if "confirm" in text_l:
        action_items.append("Send a confirmation reply.")
    if "review" in text_l:
        action_items.append("Review the requested material.")
    if "reply" in text_l or "respond" in text_l:
        action_items.append("Reply if a response is expected.")

    return summary, " | ".join(action_items[:3])


def _generate_demo_summary(email: Email) -> Optional[tuple[str, str]]:
    if not (email.external_id or "").startswith("mock-"):
        return None

    sender = (email.sender or "").strip().lower()
    subject = (email.subject or "").strip()
    subject_l = subject.lower()

    context_label = ""
    if ": " in subject:
        context_label = subject.split(": ", 1)[1].strip()

    summary = ""
    action_items: list[str] = []

    if sender == "manager@company.com" and subject_l.startswith("please confirm the delivery timeline"):
        summary = _with_context(
            "Manager needs a delivery-risk confirmation before the steering call",
            context_label,
        )
        action_items = [
            "Review remaining tasks for schedule risk.",
            "Confirm whether design sign-off is complete.",
            "Reply with blockers and the soonest realistic date if timing slipped.",
        ]
    elif sender == "alerts@service.com" and subject_l.startswith("action required: security review"):
        summary = _with_context(
            "Security flagged unusual admin logins and needs sign-off today",
            context_label,
        )
        action_items = [
            "Review the flagged sessions in the access report.",
            "Remove any permissions that should no longer be active.",
            "Confirm final status before the audit deadline.",
        ]
    elif sender == "teammate@company.com" and subject_l.startswith("project thread update"):
        summary = _with_context(
            "Design is approved, but the rollout checklist still needs review before release notes go out",
            context_label,
        )
        action_items = [
            "Review the customer support rollout checklist.",
            "Confirm ownership for weekend monitoring.",
            "Send any edits before tomorrow morning.",
        ]
    elif sender == "newsletter@weekly.io" and subject_l.startswith("weekly digest: product updates"):
        summary = _with_context(
            "Weekly digest shares product metrics and planning notes with no immediate action required",
            context_label,
        )
        action_items = [
            "Skim the onboarding drop-off section before planning.",
        ]
    elif sender == "noreply@platform.com" and subject_l.startswith("subscription offer this week"):
        summary = _with_context(
            "Promotional storage upgrade offer includes pricing and retention options, but no urgent action is needed",
            context_label,
        )
        action_items = [
            "Review plan pricing before renewal if storage is a concern.",
        ]
    elif sender == "manager@company.com" and subject_l.startswith("customer escalation for review"):
        summary = _with_context(
            "Manager needs a short recovery-plan summary for a customer escalation by noon",
            context_label,
        )
        action_items = [
            "Review the incident notes and root cause summary.",
            "Draft two customer-facing bullet points.",
            "Send the recovery-plan input before noon.",
        ]
    elif sender == "teammate@company.com" and subject_l.startswith("notes from vendor call"):
        summary = _with_context(
            "Vendor is ready to proceed once we confirm the event schema and retry behavior",
            context_label,
        )
        action_items = [
            "Review the proposed payload fields.",
            "Confirm the retry behavior and webhook ordering approach.",
            "Send approval so the vendor can start next week.",
        ]
    elif sender == "alerts@service.com" and subject_l.startswith("reminder: backup policy review"):
        summary = _with_context(
            "Backup policy changes need review before Friday approval",
            context_label,
        )
        action_items = [
            "Check the proposed retention window against legal requirements.",
            "Confirm whether the on-call rotation should change.",
            "Reply before the document is locked for approval.",
        ]

    if not summary:
        return None
    return _finalize_summary(summary), " | ".join(action_items[:3])


def _generate_llm_summary(email: Email, compact: str) -> Optional[tuple[str, str]]:
    provider = settings.summary_provider.strip().lower()

    try:
        if provider == "openai":
            return _call_openai_compatible(email, compact)
        if provider == "ollama":
            return _call_ollama(email, compact)
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response else "unknown"
        response_text = _trim_log_text(exc.response.text if exc.response else "")
        logger.warning(
            "Busy summary LLM request failed with HTTP %s for provider=%s model=%s body=%s",
            status_code,
            provider,
            settings.summary_model.strip(),
            response_text,
        )
        return None
    except httpx.RequestError as exc:
        logger.warning(
            "Busy summary LLM request error for provider=%s model=%s error=%s",
            provider,
            settings.summary_model.strip(),
            str(exc),
        )
        return None
    except Exception:
        logger.exception(
            "Busy summary LLM failed unexpectedly for provider=%s model=%s",
            provider,
            settings.summary_model.strip(),
        )
        return None

    return None


def _call_openai_compatible(email: Email, compact: str) -> Optional[tuple[str, str]]:
    model = settings.summary_model.strip()
    api_key = settings.summary_api_key.strip()
    if not model or not api_key:
        return None

    base_url = settings.summary_api_base_url.rstrip("/")
    prompt = _build_prompt(email, compact)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }

    with httpx.Client(timeout=settings.summary_timeout_seconds) as client:
        response = client.post(f"{base_url}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    message = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return _parse_summary_payload(message)


def _call_ollama(email: Email, compact: str) -> Optional[tuple[str, str]]:
    model = settings.summary_model.strip()
    if not model:
        return None

    base_url = settings.summary_api_base_url.rstrip("/")
    payload = {
        "model": model,
        "prompt": f"{_system_prompt()}\n\n{_build_prompt(email, compact)}",
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2},
    }

    with httpx.Client(timeout=settings.summary_timeout_seconds) as client:
        response = client.post(f"{base_url}/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()

    return _parse_summary_payload(data.get("response", ""))


def _build_prompt(email: Email, compact: str) -> str:
    trimmed = compact[: settings.summary_max_input_chars]
    return (
        "Summarize this email for a busy user.\n"
        "Return strict JSON with keys summary and action_items.\n"
        "summary must be one sentence, under 160 characters, no markdown.\n"
        "action_items must be an array of 0 to 3 short strings.\n"
        "Each action item should be a concrete next step for the recipient.\n"
        "Use empty array when there is no clear action.\n\n"
        f"Sender: {email.sender.strip()}\n"
        f"Subject: {email.subject.strip()}\n"
        f"Email:\n{trimmed}"
    )


def _system_prompt() -> str:
    return (
        "You write concise inbox summaries and extract recipient action items."
        " Focus on what changed, what matters, and whether the recipient needs to act."
    )


def _parse_summary_payload(raw_content: Any) -> Optional[tuple[str, str]]:
    if isinstance(raw_content, list):
        raw_content = "".join(
            part.get("text", "") for part in raw_content if isinstance(part, dict)
        )

    if not isinstance(raw_content, str) or not raw_content.strip():
        return None

    parsed = _extract_json_object(raw_content)
    if not parsed:
        return None

    summary = " ".join(str(parsed.get("summary", "")).split()).strip()
    if not summary:
        return None

    summary = summary[:160].rstrip(". ")
    action_items_raw = parsed.get("action_items", [])
    if isinstance(action_items_raw, str):
        action_items = [item.strip() for item in action_items_raw.split("|") if item.strip()]
    elif isinstance(action_items_raw, list):
        action_items = [" ".join(str(item).split()) for item in action_items_raw if str(item).strip()]
    else:
        action_items = []

    return summary + ".", " | ".join(action_items[:3])


def _extract_json_object(raw_content: str) -> Optional[dict[str, Any]]:
    try:
        parsed = json.loads(raw_content)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_content, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


def _trim_log_text(value: str, limit: int = 280) -> str:
    compact = " ".join(value.split()).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _with_context(base_summary: str, context_label: str) -> str:
    if not context_label:
        return base_summary
    return f"{base_summary} for {context_label}"


def _finalize_summary(summary: str) -> str:
    normalized = " ".join(summary.split()).strip()
    if not normalized:
        return ""
    normalized = normalized[:160].rstrip(". ")
    return normalized + "."
