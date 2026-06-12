"""SQLite database access via raw SQL (no ORM)."""

from __future__ import annotations

import json
import logging
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, TypedDict

_logger = logging.getLogger("database")

DEFAULT_SQLITE_URL = "sqlite:///./app/data/users.db"

DEFAULT_CHART_TYPE = os.getenv("DEFAULT_PREFERRED_CHART_TYPE", "bar")

VALID_CHART_TYPES = frozenset({"bar", "line", "pie"})
VALID_THEMES = frozenset({"light", "dark"})


class UserRow(TypedDict):
    id: str
    api_key: str
    email: str | None
    created_at: str
    last_used_at: str | None
    is_active: int


class PreferencesRow(TypedDict, total=False):
    user_id: str
    preferred_chart_type: str
    theme: str
    default_email: str | None
    company_logo_url: str | None
    timezone: str
    extra: str


def default_preferences() -> dict[str, Any]:
    return {
        "preferred_chart_type": DEFAULT_CHART_TYPE,
        "theme": "light",
        "default_email": None,
        "company_logo_url": None,
        "timezone": "UTC",
        "extra": {},
    }


def resolve_db_path() -> Path:
    """Resolve SQLite file path from DATABASE_URL."""
    url = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)
    if not url.startswith("sqlite:///"):
        _logger.warning(
            "DATABASE_URL is not SQLite (%s); falling back to %s",
            url.split("://", 1)[0],
            DEFAULT_SQLITE_URL,
        )
        url = DEFAULT_SQLITE_URL

    raw = url.removeprefix("sqlite:///")
    path = Path(raw)
    if not path.is_absolute():
        # WORKDIR is /app in Docker; ./app/data -> /app/app/data
        path = Path.cwd() / path
    return path


def mask_api_key(api_key: str) -> str:
    """Return masked API key for logging (last 4 chars only)."""
    if len(api_key) <= 4:
        return "****"
    return f"****{api_key[-4:]}"


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    db_path = resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row_to_user(row: sqlite3.Row) -> UserRow:
    return UserRow(
        id=row["id"],
        api_key=row["api_key"],
        email=row["email"],
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        is_active=row["is_active"],
    )


def _parse_preferences_row(row: sqlite3.Row | None) -> dict[str, Any]:
    defaults = default_preferences()
    if row is None:
        return defaults

    extra_raw = row["extra"] if row["extra"] else "{}"
    try:
        extra = json.loads(extra_raw)
    except json.JSONDecodeError:
        extra = {}

    return {
        "preferred_chart_type": row["preferred_chart_type"] or defaults["preferred_chart_type"],
        "theme": row["theme"] or defaults["theme"],
        "default_email": row["default_email"],
        "company_logo_url": row["company_logo_url"],
        "timezone": row["timezone"] or defaults["timezone"],
        "extra": extra if isinstance(extra, dict) else {},
    }


def create_user(email: str | None = None) -> tuple[str, str]:
    """Create user with new API key. Returns (user_id, api_key)."""
    user_id = str(uuid.uuid4())
    api_key = secrets.token_urlsafe(32)

    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (id, api_key, email) VALUES (?, ?, ?)",
            (user_id, api_key, email),
        )
        conn.execute(
            """
            INSERT INTO preferences (user_id, preferred_chart_type, theme, timezone, extra)
            VALUES (?, ?, 'light', 'UTC', '{}')
            """,
            (user_id, DEFAULT_CHART_TYPE),
        )

    return user_id, api_key


def get_user_by_api_key(api_key: str) -> UserRow | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE api_key = ?",
            (api_key,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_user(row)


def get_user_by_id(user_id: str) -> UserRow | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        return None
    return _row_to_user(row)


def update_last_used_at(user_id: str) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET last_used_at = ? WHERE id = ?",
            (now, user_id),
        )


def get_user_preferences(user_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    prefs = _parse_preferences_row(row)

    user = get_user_by_id(user_id)
    if user and user["email"] and not prefs.get("default_email"):
        prefs["default_email"] = user["email"]

    return prefs


def get_preferences_by_api_key(api_key: str) -> dict[str, Any] | None:
    user = get_user_by_api_key(api_key)
    if user is None or not user["is_active"]:
        return None
    return get_user_preferences(user["id"])


def update_user_preferences(user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "preferred_chart_type",
        "theme",
        "default_email",
        "company_logo_url",
        "timezone",
        "extra",
    }
    filtered = {k: v for k, v in updates.items() if k in allowed and v is not None}

    if "preferred_chart_type" in filtered:
        if filtered["preferred_chart_type"] not in VALID_CHART_TYPES:
            raise ValueError(
                f"preferred_chart_type must be one of: {', '.join(sorted(VALID_CHART_TYPES))}"
            )

    if "theme" in filtered:
        if filtered["theme"] not in VALID_THEMES:
            raise ValueError(f"theme must be one of: {', '.join(sorted(VALID_THEMES))}")

    if "extra" in filtered and not isinstance(filtered["extra"], dict):
        raise ValueError("extra must be a JSON object")

    with get_connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM preferences WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if not exists:
            conn.execute(
                """
                INSERT INTO preferences (user_id, preferred_chart_type, theme, timezone, extra)
                VALUES (?, ?, 'light', 'UTC', '{}')
                """,
                (user_id, DEFAULT_CHART_TYPE),
            )

        set_parts: list[str] = []
        values: list[Any] = []
        for key, value in filtered.items():
            if key == "extra":
                set_parts.append("extra = ?")
                values.append(json.dumps(value))
            else:
                set_parts.append(f"{key} = ?")
                values.append(value)

        if set_parts:
            values.append(user_id)
            conn.execute(
                f"UPDATE preferences SET {', '.join(set_parts)} WHERE user_id = ?",
                values,
            )

    return get_user_preferences(user_id)


def reset_user_preferences(user_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE preferences SET
                preferred_chart_type = ?,
                theme = 'light',
                default_email = NULL,
                company_logo_url = NULL,
                timezone = 'UTC',
                extra = '{}'
            WHERE user_id = ?
            """,
            (DEFAULT_CHART_TYPE, user_id),
        )
    return get_user_preferences(user_id)


def get_usage_count(user_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM history WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return int(row["cnt"]) if row else 0


def log_history(
    user_id: str,
    request_summary: str,
    task_id: str | None = None,
) -> None:
    summary = request_summary[:100] if request_summary else ""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO history (user_id, task_id, request_summary)
            VALUES (?, ?, ?)
            """,
            (user_id, task_id, summary),
        )


def resolve_email_for_user(
    user_id: str,
    request_email: str | None,
) -> str | None:
    """Pick email: request > preferences.default_email > users.email."""
    if request_email:
        return request_email

    prefs = get_user_preferences(user_id)
    if prefs.get("default_email"):
        return prefs["default_email"]

    user = get_user_by_id(user_id)
    if user and user["email"]:
        return user["email"]

    return None
