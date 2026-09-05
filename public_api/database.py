"""Shared, read-only database configuration for the public API and release gate."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from urllib.parse import quote


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = REPO_ROOT / "analyzeCourseFeedback" / "course_feedback.db"
DB_PATH_ENV = "COURSE_FEEDBACK_DB_PATH"


def configured_database_path(explicit_path: str | os.PathLike[str] | None = None) -> Path:
    """Return an injected path, the environment override, or the local repo default."""

    if explicit_path is not None:
        return Path(explicit_path).expanduser().resolve()
    configured = os.environ.get(DB_PATH_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_DB_PATH.resolve()


@contextmanager
def connect_read_only(database_path: str | os.PathLike[str]) -> Iterator[sqlite3.Connection]:
    """Open SQLite in URI read-only mode and additionally enforce query-only mode."""

    path = Path(database_path).expanduser().resolve()
    uri = f"file:{quote(str(path), safe='/')}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    try:
        yield connection
    finally:
        connection.close()
