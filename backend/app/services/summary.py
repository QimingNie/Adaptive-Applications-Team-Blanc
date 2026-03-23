import json
import re
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.models import Email


def generate_busy_summary(email: Email, allow_llm: bool = True) -> tuple[str, str]:
    compact = _compact_email_text(email)
    if not compact:
        return "No content available.", ""

    if allow_llm and _llm_enabled(compact):
        llm_result = _generate_llm_summary(email, compact)
        if llm_result:
            return llm_result

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


def _generate_llm_summary(email: Email, compact: str) -> Optional[tuple[str, str]]:
    provider = settings.summary_provider.strip().lower()

    try:
        if provider == "openai":
            return _call_openai_compatible(email, compact)
        if provider == "ollama":
            return _call_ollama(email, compact)
    except Exception:
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
