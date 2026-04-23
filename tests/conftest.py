"""Shared pytest fixtures.

Each test configures isolated SQLite + test env vars so nothing leaks
between tests or reaches the real Groq API.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

# Ensure the project root is importable when running `pytest` from anywhere.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    db_path = tmp_path / "apilog.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("RATE_LIMIT_STORAGE_URI", "memory://")
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    # Reset cached settings so the new env vars take effect.
    from config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def flask_app():  # type: ignore[no-untyped-def]
    from app import create_app

    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture()
def client(flask_app):  # type: ignore[no-untyped-def]
    return flask_app.test_client()
