"""SQLite database access via raw SQL (no ORM)."""

from __future__ import annotations

import hashlib
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
DEFAULT_OUTPUT_FORMAT = os.getenv("DEFAULT_OUTPUT_FORMAT", "pdf").strip().lower()

VALID_CHART_TYPES = frozenset({"bar", "line", "pie"})
VALID_THEMES = frozenset({"light", "dark"})
VALID_OUTPUT_FORMATS = frozenset(
    fmt.strip().lower()
    for fmt in os.getenv(
        "ALLOWED_OUTPUT_FORMATS",
        "pdf,excel,pptx,notion,google_slides",
    ).split(",")
    if fmt.strip()
)


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
        "default_output_format": DEFAULT_OUTPUT_FORMAT,
        "extra": {},
    }


def resolve_db_path() -> Path:
    """Resolve SQLite file path from DATABASE_URL."""
    url = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URL)
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        _logger.info("PostgreSQL DATABASE_URL detected — using SQLite fallback unless PG adapter is wired")
        url = DEFAULT_SQLITE_URL
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
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
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
        "default_output_format": (
            row["default_output_format"]
            if "default_output_format" in row.keys() and row["default_output_format"]
            else defaults["default_output_format"]
        ),
        "last_plan_notification_shown": (
            row["last_plan_notification_shown"]
            if "last_plan_notification_shown" in row.keys()
            else None
        ),
        "extra": extra if isinstance(extra, dict) else {},
        "last_plan_notification_shown": (
            row["last_plan_notification_shown"]
            if "last_plan_notification_shown" in row.keys()
            else None
        ),
    }


def create_user(email: str | None = None, name: str = "Default") -> tuple[str, str, str]:
    """Create user with new API key. Returns (user_id, api_key, key_id)."""
    user_id = str(uuid.uuid4())
    api_key = f"ra_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    key_prefix = api_key[:8]
    key_id = str(uuid.uuid4())

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
        try:
            conn.execute(
                """
                INSERT INTO api_keys (
                    id, user_id, key_hash, key_prefix, name, is_active
                ) VALUES (?, ?, ?, ?, ?, 1)
                """,
                (key_id, user_id, key_hash, key_prefix, name),
            )
        except sqlite3.OperationalError:
            pass

    return user_id, api_key, key_id


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
    from app.auth.key_management import verify_api_key

    auth = verify_api_key(api_key)
    if auth is None:
        return None
    user = get_user_by_id(auth["user_id"])
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
        "default_output_format",
        "last_plan_notification_shown",
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

    if "default_output_format" in filtered:
        fmt = str(filtered["default_output_format"]).strip().lower()
        if fmt not in VALID_OUTPUT_FORMATS:
            raise ValueError(
                f"default_output_format must be one of: {', '.join(sorted(VALID_OUTPUT_FORMATS))}"
            )
        filtered["default_output_format"] = fmt

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
                default_output_format = ?,
                extra = '{}'
            WHERE user_id = ?
            """,
            (DEFAULT_CHART_TYPE, DEFAULT_OUTPUT_FORMAT, user_id),
        )
    return get_user_preferences(user_id)


def count_active_users(days: int = 30) -> int:
    """Count users active within the last N days (by last_used_at or created_at)."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM users
            WHERE is_active = 1
              AND (
                (last_used_at IS NOT NULL AND datetime(last_used_at) >= datetime('now', ?))
                OR (last_used_at IS NULL AND datetime(created_at) >= datetime('now', ?))
              )
            """,
            (f"-{days} days", f"-{days} days"),
        ).fetchone()
    return int(row["cnt"]) if row else 0


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
    request_type: str = "api",
    output_format: str | None = None,
) -> None:
    summary = request_summary[:100] if request_summary else ""
    fmt = (output_format or DEFAULT_OUTPUT_FORMAT).strip().lower()
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO history (user_id, task_id, request_summary, request_type, output_format)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, task_id, summary, request_type, fmt),
            )
        except sqlite3.OperationalError:
            try:
                conn.execute(
                    """
                    INSERT INTO history (user_id, task_id, request_summary, request_type)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, task_id, summary, request_type),
                )
            except sqlite3.OperationalError:
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


def update_history_task_result(
    user_id: str,
    task_id: str,
    *,
    status: str,
    duration_seconds: float | None = None,
) -> None:
    """Update history row when a Celery report task completes or fails."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE history
            SET status = ?, duration_seconds = ?
            WHERE user_id = ? AND task_id = ?
            """,
            (status, duration_seconds, user_id, task_id),
        )


def _report_history_filter(alias: str = "") -> str:
    """SQL fragment: rows that represent report generation (not webhooks / misc)."""
    prefix = f"{alias}." if alias else ""
    return (
        f"{prefix}user_id = ? AND {prefix}task_id IS NOT NULL AND {prefix}task_id != '' "
        f"AND ({prefix}request_type IS NULL OR {prefix}request_type != 'webhook_sent')"
    )


def _latest_reports_subquery() -> str:
    """One row per task_id (most recent history id)."""
    return f"""
        SELECT h.task_id, h.request_summary, h.created_at, h.output_format, h.status, h.duration_seconds
        FROM history h
        INNER JOIN (
            SELECT task_id, MAX(id) AS max_id
            FROM history
            WHERE {_report_history_filter()}
            GROUP BY task_id
        ) latest ON h.id = latest.max_id
    """


def get_dashboard_stats(user_id: str) -> dict[str, Any]:
    """Aggregate dashboard metrics for the last 30 days."""
    latest = _latest_reports_subquery()
    with get_connection() as conn:
        total_row = conn.execute(
            f"""
            SELECT COUNT(*) AS cnt FROM ({latest}) reports
            WHERE datetime(created_at) >= datetime('now', '-30 days')
            """,
            (user_id,),
        ).fetchone()

        outcome_row = conn.execute(
            f"""
            SELECT
                SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS successes,
                SUM(CASE WHEN status IN ('SUCCESS', 'FAILURE') THEN 1 ELSE 0 END) AS finished
            FROM ({latest}) reports
            WHERE datetime(created_at) >= datetime('now', '-30 days')
            """,
            (user_id,),
        ).fetchone()

        format_row = conn.execute(
            f"""
            SELECT COALESCE(output_format, 'pdf') AS fmt, COUNT(*) AS cnt
            FROM ({latest}) reports
            WHERE datetime(created_at) >= datetime('now', '-30 days')
            GROUP BY fmt
            ORDER BY cnt DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

        avg_row = conn.execute(
            f"""
            SELECT AVG(duration_seconds) AS avg_sec
            FROM ({latest}) reports
            WHERE status = 'SUCCESS'
              AND duration_seconds IS NOT NULL
              AND datetime(created_at) >= datetime('now', '-30 days')
            """,
            (user_id,),
        ).fetchone()

        try:
            webhook_row = conn.execute(
                """
                SELECT COUNT(*) AS cnt FROM webhooks
                WHERE user_id = ? AND is_active = 1
                """,
                (user_id,),
            ).fetchone()
        except Exception:
            webhook_row = {"cnt": 0}

    total = int(total_row["cnt"]) if total_row else 0
    successes = int(outcome_row["successes"] or 0) if outcome_row else 0
    finished = int(outcome_row["finished"] or 0) if outcome_row else 0
    success_rate = round((successes / finished) * 100, 1) if finished else 0.0
    most_format = format_row["fmt"] if format_row else "pdf"
    avg_time = avg_row["avg_sec"] if avg_row and avg_row["avg_sec"] is not None else None

    return {
        "total_reports_last_30_days": total,
        "success_rate": success_rate,
        "most_used_output_format": most_format,
        "average_generation_time_seconds": round(float(avg_time), 1) if avg_time is not None else 0.0,
        "active_webhooks_count": int(webhook_row["cnt"]) if webhook_row else 0,
    }


def list_user_reports(
    user_id: str,
    *,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """Return paginated report history rows and total count."""
    page = max(1, page)
    limit = max(1, min(limit, 100))
    offset = (page - 1) * limit
    latest = _latest_reports_subquery()

    with get_connection() as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM ({latest}) reports",
            (user_id,),
        ).fetchone()
        rows = conn.execute(
            f"""
            SELECT task_id, request_summary, created_at, output_format, status
            FROM ({latest}) reports
            ORDER BY datetime(created_at) DESC
            LIMIT ? OFFSET ?
            """,
            (user_id, limit, offset),
        ).fetchall()

    total = int(total_row["cnt"]) if total_row else 0
    reports: list[dict[str, Any]] = []
    for row in rows:
        output_format = row["output_format"] or "pdf"
        task_id = row["task_id"] or ""
        reports.append(
            {
                "task_id": task_id,
                "created_at": row["created_at"],
                "status": row["status"] or "PENDING",
                "output_format": output_format,
                "download_url": _download_path_for_format(task_id, output_format),
                "request_summary": row["request_summary"] or "",
            }
        )
    return reports, total


def _download_path_for_format(task_id: str, output_format: str) -> str:
    if output_format == "pdf":
        return f"/tasks/{task_id}/pdf"
    return f"/tasks/{task_id}/export"


def delete_user_report(user_id: str, task_id: str) -> bool:
    """Delete history row for user/task. Returns False if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM history WHERE user_id = ? AND task_id = ?",
            (user_id, task_id),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "DELETE FROM history WHERE user_id = ? AND task_id = ?",
            (user_id, task_id),
        )
    return True
