from datetime import datetime

from app.models import Email
from app.services import summary


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return self._responses.pop(0)


def _email(external_id: str = "mail-1") -> Email:
    return Email(
        external_id=external_id,
        sender="alerts@service.com",
        subject="Reminder: backup policy review: Atlas Rollout",
        snippet="The backup policy review is due Friday and leadership wants a firmer handoff plan.",
        body=(
            "The backup policy review is due Friday and the current retention window needs approval. "
            "Leadership asked for a firmer handoff plan before the launch freeze. "
            "Please confirm whether the legal requirements are covered and whether the on-call rotation changes."
        ),
        received_at=datetime.utcnow(),
        bucket="later",
    )


def test_openai_compatible_retries_without_response_format(monkeypatch):
    fake_client = _FakeClient(
        [
            _FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": None,
                            }
                        }
                    ]
                }
            ),
            _FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"summary":"Backup policy review due Friday.",' \
                                    '"action_items":["Review the policy notes"]}'
                                )
                            }
                        }
                    ]
                }
            ),
        ]
    )

    monkeypatch.setattr(summary.httpx, "Client", lambda timeout: fake_client)
    monkeypatch.setattr(summary.settings, "summary_model", "minimax/minimax-m2.5:free")
    monkeypatch.setattr(summary.settings, "summary_api_key", "test-key")
    monkeypatch.setattr(summary.settings, "summary_api_base_url", "https://openrouter.ai/api/v1")
    monkeypatch.setattr(summary.settings, "summary_timeout_seconds", 12)

    result = summary._call_openai_compatible(_email(), summary._compact_email_text(_email()))

    assert result == ("Backup policy review due Friday.", "Review the policy notes")
    assert len(fake_client.calls) == 2
    assert "response_format" in fake_client.calls[0]["json"]
    assert "response_format" not in fake_client.calls[1]["json"]


def test_summary_refreshes_when_current_summary_matches_non_llm_fallback(monkeypatch):
    email = _email(external_id="mock-123")
    fallback_summary, fallback_actions = summary.generate_busy_summary(email, allow_llm=False)
    email.busy_summary = fallback_summary
    email.action_items = fallback_actions

    monkeypatch.setattr(summary, "_llm_enabled", lambda compact: True)

    assert summary.summary_needs_refresh(email) is True