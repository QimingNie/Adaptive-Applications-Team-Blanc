import os
from pathlib import Path

from pydantic import BaseModel
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "Smart Inbox API")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./smart_inbox.db")
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://127.0.0.1:8000/api/auth/google/callback"
    )
    frontend_oauth_done_uri: str = os.getenv(
        "FRONTEND_OAUTH_DONE_URI", "http://127.0.0.1:5173/"
    )


settings = Settings()
