"""Admin database queries: users, audit, rate limits."""

from __future__ import annotations

import json
from typing import Any

from app.db.database import get_connection, get_user_preferences

GLOBAL_SCOPE = "__global__"


def insert_audit_log(
    *,
    action: str,
    target: str | None = None,
    details: str | None = None,
    admin_ip: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_log (admin_ip, action, target, details)
            VALUES (?, ?, ?, ?)
            """,
            (admin_ip, action, target, details),
        )


def get_global_rate_limit() -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT limit_per_minute FROM rate_limits WHERE scope_id = ?",
            (GLOBAL_SCOPE,),
        ).fetchone()
    return int(row["limit_per_minute"]) if row else 100


def set_global_rate_limit(limit: int) -> int:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO rate_limits (scope_id, limit_per_minute, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(scope_id) DO UPDATE SET
                limit_per_minute = excluded.limit_per_minute,
                updated_at = CURRENT_TIMESTAMP
            """,
            (GLOBAL_SCOPE, limit),
        )
    return limit


def get_user_rate_limit(user_id: str) -> int | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT limit_per_minute FROM rate_limits WHERE scope_id = ?",
            (user_id,),
        ).fetchone()
    return int(row["limit_per_minute"]) if row else None


def set_user_rate_limit(user_id: str, limit: int) -> int:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO rate_limits (scope_id, limit_per_minute, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(scope_id) DO UPDATE SET
                limit_per_minute = excluded.limit_per_minute,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, limit),
        )
    return limit


def list_rate_limits() -> dict[str, Any]:
    global_limit = get_global_rate_limit()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT scope_id, limit_per_minute FROM rate_limits WHERE scope_id != ?",
            (GLOBAL_SCOPE,),
        ).fetchall()
    return {
        "global_limit": global_limit,
        "user_limits": [
            {"user_id": row["scope_id"], "limit": int(row["limit_per_minute"])}
            for row in rows
        ],
    }


def _user_success_rate(conn, user_id: str) -> float:
    row = conn.execute(
        """
        SELECT
            SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) AS successes,
            SUM(CASE WHEN status IN ('SUCCESS', 'FAILURE') THEN 1 ELSE 0 END) AS finished
        FROM history
        WHERE user_id = ? AND task_id IS NOT NULL AND task_id != ''
        """,
        (user_id,),
    ).fetchone()
    successes = int(row["successes"] or 0) if row else 0
    finished = int(row["finished"] or 0) if row else 0
    return round((successes / finished) * 100, 1) if finished else 0.0


def _user_key_counts(conn, user_id: str) -> tuple[int, int]:
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) AS active
            FROM api_keys WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
        return int(row["total"] or 0), int(row["active"] or 0)
    except Exception:
        return 0, 0


def list_users_admin(
    *,
    page: int = 1,
    limit: int = 50,
    search: str | None = None,
    is_active: str = "all",
    include_preferences: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    page = max(1, page)
    limit = max(1, min(limit, 200))
    offset = (page - 1) * limit

    conditions: list[str] = []
    params: list[Any] = []

    if search:
        conditions.append("(u.email LIKE ? OR u.id LIKE ?)")
        pattern = f"%{search}%"
        params.extend([pattern, pattern])

    if is_active == "true":
        conditions.append("u.is_active = 1")
    elif is_active == "false":
        conditions.append("u.is_active = 0")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with get_connection() as conn:
        total_row = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM users u {where}",
            params,
        ).fetchone()
        rows = conn.execute(
            f"""
            SELECT u.id, u.email, u.created_at, u.last_used_at, u.is_active,
                   (SELECT COUNT(*) FROM history h WHERE h.user_id = u.id) AS total_requests
            FROM users u
            {where}
            ORDER BY datetime(u.created_at) DESC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()

        users: list[dict[str, Any]] = []
        for row in rows:
            total_keys, active_keys = _user_key_counts(conn, row["id"])
            item: dict[str, Any] = {
                "id": row["id"],
                "email": row["email"],
                "created_at": row["created_at"],
                "last_used_at": row["last_used_at"],
                "is_active": bool(row["is_active"]),
                "total_requests": int(row["total_requests"] or 0),
                "success_rate": _user_success_rate(conn, row["id"]),
                "total_keys": total_keys,
                "active_keys": active_keys,
            }
            if include_preferences:
                item["preferences"] = get_user_preferences(row["id"])
            users.append(item)

    return users, int(total_row["cnt"]) if total_row else 0


def get_user_detail_admin(user_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None

        keys = conn.execute(
            """
            SELECT id, key_prefix, name, created_at, last_used_at, expires_at, is_active
            FROM api_keys WHERE user_id = ? ORDER BY datetime(created_at) DESC
            """,
            (user_id,),
        ).fetchall()

        history_rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT id, task_id, request_summary, created_at, request_type,
                       output_format, status, duration_seconds
                FROM history
                WHERE user_id = ?
                ORDER BY datetime(created_at) DESC
                LIMIT 20
                """,
                (user_id,),
            ).fetchall()
        ]

        failure_row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM history
            WHERE user_id = ? AND status = 'FAILURE'
            """,
            (user_id,),
        ).fetchone()
        success_row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM history
            WHERE user_id = ? AND status = 'SUCCESS'
            """,
            (user_id,),
        ).fetchone()

    from app.webhook.registration import get_webhooks_for_user

    webhooks = get_webhooks_for_user(user_id)

    with get_connection() as conn:
        total_keys, active_keys = _user_key_counts(conn, user_id)
        success_rate = _user_success_rate(conn, user_id)

    return {
        "id": row["id"],
        "email": row["email"],
        "created_at": row["created_at"],
        "last_used_at": row["last_used_at"],
        "is_active": bool(row["is_active"]),
        "total_requests": len(history_rows),
        "success_rate": success_rate,
        "total_keys": total_keys,
        "active_keys": active_keys,
        "api_keys": [
            {
                "id": k["id"],
                "key_prefix": k["key_prefix"],
                "name": k["name"],
                "created_at": k["created_at"],
                "last_used_at": k["last_used_at"],
                "expires_at": k["expires_at"],
                "is_active": bool(k["is_active"]),
            }
            for k in keys
        ],
        "recent_history": history_rows,
        "preferences": get_user_preferences(user_id),
        "webhooks": webhooks,
        "self_healing": {
            "report_failures": int(failure_row["cnt"]) if failure_row else 0,
            "report_successes": int(success_row["cnt"]) if success_row else 0,
            "note": "Self-healing knowledge base is global; per-user fix counts are not tracked separately.",
        },
    }


def block_user_admin(user_id: str) -> tuple[int, bool]:
    """Block user and revoke all active keys. Returns (keys_revoked, found)."""
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return 0, False

        conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        cur = conn.execute(
            "UPDATE api_keys SET is_active = 0 WHERE user_id = ? AND is_active = 1",
            (user_id,),
        )
        return cur.rowcount, True


def unblock_user_admin(user_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return False
        conn.execute("UPDATE users SET is_active = 1 WHERE id = ?", (user_id,))
        return True


def delete_user_admin(user_id: str) -> dict[str, int] | None:
    """Delete user and related rows. Returns counts or None if not found."""
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return None

        reports = conn.execute(
            "SELECT COUNT(*) AS cnt FROM history WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        keys = conn.execute(
            "SELECT COUNT(*) AS cnt FROM api_keys WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        # history.user_id has no ON DELETE CASCADE (001_init.sql)
        conn.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        conn.execute(
            "DELETE FROM rate_limits WHERE scope_id = ? AND scope_id != '__global__'",
            (user_id,),
        )
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    return {
        "reports_count": int(reports["cnt"]) if reports else 0,
        "keys_count": int(keys["cnt"]) if keys else 0,
    }


def count_all_users() -> tuple[int, int]:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
        active = conn.execute(
            "SELECT COUNT(*) AS cnt FROM users WHERE is_active = 1"
        ).fetchone()
    return int(total["cnt"]) if total else 0, int(active["cnt"]) if active else 0
