from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings

_connect_args = {"check_same_thread": False}
_engine_kwargs: dict = {"connect_args": _connect_args}
# :memory: uses a fresh DB per SQLite connection unless we pin a single shared connection.
if settings.database_url.startswith("sqlite") and ":memory:" in settings.database_url:
    _engine_kwargs["poolclass"] = StaticPool

engine = create_engine(settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
