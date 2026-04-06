import os
from pathlib import Path

from pydantic import BaseModel
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def _resolve_sqlite_url(url: str, base: Path) -> str:
    """Pin relative sqlite files to backend/ so cwd does not split sync vs inbox across DBs."""
    u = (url or "").strip()
    if not u.startswith("sqlite:///"):
        return u
    if ":memory:" in u:
        return u
    path_part = u[len("sqlite:///") :]
    p = Path(path_part)
    if not p.is_absolute():
        p = (base / p).resolve()
    return f"sqlite:///{p.as_posix()}"


_RAW_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./smart_inbox.db")


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "Smart Inbox API")
    database_url: str = _resolve_sqlite_url(_RAW_DATABASE_URL, BASE_DIR)
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://127.0.0.1:8010/api/auth/google/callback"
    )
    frontend_oauth_done_uri: str = os.getenv(
        "FRONTEND_OAUTH_DONE_URI", "http://127.0.0.1:5173/"
    )
    summary_provider: str = os.getenv("SUMMARY_PROVIDER", "off")
    summary_model: str = os.getenv("SUMMARY_MODEL", "")
    summary_api_base_url: str = os.getenv("SUMMARY_API_BASE_URL", "https://api.openai.com/v1")
    summary_api_key: str = os.getenv("SUMMARY_API_KEY", "")
    summary_timeout_seconds: float = float(os.getenv("SUMMARY_TIMEOUT_SECONDS", "12"))
    summary_max_input_chars: int = int(os.getenv("SUMMARY_MAX_INPUT_CHARS", "1800"))
    summary_min_llm_chars: int = int(os.getenv("SUMMARY_MIN_LLM_CHARS", "280"))


settings = Settings()
