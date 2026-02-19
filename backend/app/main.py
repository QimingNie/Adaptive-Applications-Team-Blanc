from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.routes import router
from app.db import Base, engine

Base.metadata.create_all(bind=engine)


def ensure_legacy_columns():
    with engine.begin() as conn:
        inspector = inspect(conn)
        if "users" not in inspector.get_table_names():
            return
        columns = {col["name"] for col in inspector.get_columns("users")}
        if "gmail_history_id" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN gmail_history_id VARCHAR(255)"))


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


@app.get("/health")
def health():
    return {"status": "ok"}
