from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.core.config import settings
from app.api.routes import router
from app.db import Base, engine

Base.metadata.create_all(bind=engine)


def ensure_legacy_columns():
    with engine.begin() as conn:
        inspector = inspect(conn)
        tables = set(inspector.get_table_names())
        if "users" not in tables:
            return
        user_columns = {col["name"] for col in inspector.get_columns("users")}
        if "gmail_history_id" not in user_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN gmail_history_id VARCHAR(255)"))
        if "user_preferences" in tables:
            pref_columns = {col["name"] for col in inspector.get_columns("user_preferences")}
            if "feature_weights_json" not in pref_columns:
                conn.execute(text("ALTER TABLE user_preferences ADD COLUMN feature_weights_json TEXT DEFAULT ''"))


ensure_legacy_columns()

app = FastAPI(title="Smart Inbox API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/")
def root():
    return {
        "service": settings.app_name,
        "health": "/health",
        "docs": "/docs",
        "api": "/api",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
