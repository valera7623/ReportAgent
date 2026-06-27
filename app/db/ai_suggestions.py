"""Persist AI suggestions in SQLite."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from app.db.database import get_connection
from app.utils.logger import get_logger

logger = get_logger("ai_suggestions_db", "log_api.log")

DEFAULT_TTL_HOURS = 24


def save_ai_suggestions(
    user_id: str,
    file_hash: str,
    suggestions: dict[str, Any],
    *,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> int:
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    payload = json.dumps(suggestions, ensure_ascii=False)
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM ai_suggestions WHERE user_id = ? AND file_hash = ?",
            (user_id, file_hash),
        )
        cursor = conn.execute(
            """
            INSERT INTO ai_suggestions (user_id, file_hash, suggestions, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, file_hash, payload, expires_at.isoformat()),
        )
        return int(cursor.lastrowid)


def get_ai_suggestions(user_id: str, file_hash: str) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT suggestions FROM ai_suggestions
            WHERE user_id = ? AND file_hash = ? AND expires_at > ?
            ORDER BY id DESC LIMIT 1
            """,
            (user_id, file_hash, now),
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row[0])
    except json.JSONDecodeError:
        logger.warning("Invalid ai_suggestions JSON for user=%s hash=%s", user_id, file_hash)
        return None


def purge_expired_ai_suggestions() -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM ai_suggestions WHERE expires_at <= ?", (now,))
        return cursor.rowcount
