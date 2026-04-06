"""Test harness: in-memory SQLite (set before app imports bind the engine)."""

import os

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
