"""Webhook registration and persistence in SQLite."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.database import get_connection, get_user_by_id
from app.webhook.config import VALID_EVENTS
from app.webhook.url_validator import validate_webhook_url

DEFAULT_EVENTS = ["report.completed", "report.failed"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_events(raw: str | None) -> list[str]:
    if not raw:
        return list(DEFAULT_EVENTS)
    try:
        events = json.loads(raw)
    except json.JSONDecodeError:
        return list(DEFAULT_EVENTS)
    if not isinstance(events, list):
        return list(DEFAULT_EVENTS)
    return [e for e in events if e in VALID_EVENTS] or list(DEFAULT_EVENTS)


def _row_to_webhook(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "url": row["url"],
        "secret": row["secret"],
        "events": _parse_events(row["events"]),
        "created_at": row["created_at"],
        "is_active": bool(row["is_active"]),
        "last_triggered_at": row["last_triggered_at"],
        "failure_count": int(row["failure_count"] or 0),
    }


def _validate_events(events: list[str]) -> list[str]:
    if not events:
        return ["report.completed"]
    invalid = [e for e in events if e not in VALID_EVENTS]
    if invalid:
        raise ValueError(f"Invalid events: {', '.join(invalid)}. Allowed: {', '.join(sorted(VALID_EVENTS))}")
    return events


def register_webhook(
    user_id: str,
    url: str,
    secret: str | None = None,
    events: list[str] | None = None,
) -> str:
    """Register a webhook for a user. Returns webhook id."""
    validate_webhook_url(url)
    event_list = _validate_events(events or ["report.completed"])
    webhook_id = str(uuid.uuid4())
    secret_value = secret.strip() if secret else None

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO webhooks (id, user_id, url, secret, events, created_at, is_active, failure_count)
            VALUES (?, ?, ?, ?, ?, ?, 1, 0)
            """,
            (
                webhook_id,
                user_id,
                url.strip(),
                secret_value,
                json.dumps(event_list),
                _now_iso(),
            ),
        )
    return webhook_id


def unregister_webhook(webhook_id: str, user_id: str | None = None) -> bool:
    """Delete webhook registration. Returns True if deleted."""
    with get_connection() as conn:
        if user_id:
            cur = conn.execute(
                "DELETE FROM webhooks WHERE id = ? AND user_id = ?",
                (webhook_id, user_id),
            )
        else:
            cur = conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
    return cur.rowcount > 0


def get_webhook(webhook_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    with get_connection() as conn:
        if user_id:
            row = conn.execute(
                "SELECT * FROM webhooks WHERE id = ? AND user_id = ?",
                (webhook_id, user_id),
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,)).fetchone()
    if row is None:
        return None
    wh = _row_to_webhook(row)
    # Never expose secret in API responses
    wh.pop("secret", None)
    return wh


def get_webhooks_for_user(user_id: str, *, include_secret: bool = False) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM webhooks WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    result = [_row_to_webhook(row) for row in rows]
    if not include_secret:
        for wh in result:
            wh.pop("secret", None)
    return result


def get_webhooks_for_event(
    event: str,
    user_id: str | None = None,
    *,
    include_secret: bool = True,
) -> list[dict[str, Any]]:
    """Return active webhooks subscribed to the given event."""
    if event not in VALID_EVENTS:
        return []

    query = "SELECT * FROM webhooks WHERE is_active = 1"
    params: list[Any] = []
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    matched: list[dict[str, Any]] = []
    for row in rows:
        wh = _row_to_webhook(row)
        if event in wh["events"]:
            if not include_secret:
                wh.pop("secret", None)
            matched.append(wh)
    return matched


def update_webhook(
    webhook_id: str,
    user_id: str,
    *,
    url: str | None = None,
    events: list[str] | None = None,
    is_active: bool | None = None,
    secret: str | None = None,
) -> dict[str, Any] | None:
    """Update webhook fields. Returns updated webhook without secret."""
    updates: dict[str, Any] = {}
    if url is not None:
        validate_webhook_url(url)
        updates["url"] = url.strip()
    if events is not None:
        updates["events"] = json.dumps(_validate_events(events))
    if is_active is not None:
        updates["is_active"] = 1 if is_active else 0
    if secret is not None:
        updates["secret"] = secret.strip() or None

    if not updates:
        return get_webhook(webhook_id, user_id)

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [webhook_id, user_id]

    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE webhooks SET {set_clause} WHERE id = ? AND user_id = ?",
            values,
        )
        if cur.rowcount == 0:
            return None

    return get_webhook(webhook_id, user_id)


def reactivate_webhook(webhook_id: str, user_id: str) -> dict[str, Any] | None:
    """Re-enable a deactivated webhook and reset failure_count."""
    with get_connection() as conn:
        cur = conn.execute(
            """
            UPDATE webhooks
            SET is_active = 1, failure_count = 0
            WHERE id = ? AND user_id = ?
            """,
            (webhook_id, user_id),
        )
        if cur.rowcount == 0:
            return None
    return get_webhook(webhook_id, user_id)


def record_webhook_success(webhook_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE webhooks
            SET last_triggered_at = ?, failure_count = 0
            WHERE id = ?
            """,
            (_now_iso(), webhook_id),
        )


def record_webhook_failure(webhook_id: str) -> int:
    """Increment failure_count. Returns new count."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE webhooks SET failure_count = failure_count + 1 WHERE id = ?",
            (webhook_id,),
        )
        row = conn.execute(
            "SELECT failure_count FROM webhooks WHERE id = ?",
            (webhook_id,),
        ).fetchone()
    return int(row["failure_count"]) if row else 0


def deactivate_webhook(webhook_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE webhooks SET is_active = 0 WHERE id = ?",
            (webhook_id,),
        )


def get_webhook_with_secret(webhook_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM webhooks WHERE id = ?", (webhook_id,)).fetchone()
    if row is None:
        return None
    return _row_to_webhook(row)


def get_webhook_stats() -> dict[str, Any]:
    """Admin stats for all webhooks."""
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) AS cnt FROM webhooks").fetchone()["cnt"]
        active = conn.execute(
            "SELECT COUNT(*) AS cnt FROM webhooks WHERE is_active = 1"
        ).fetchone()["cnt"]
        deactivated = conn.execute(
            "SELECT COUNT(*) AS cnt FROM webhooks WHERE is_active = 0"
        ).fetchone()["cnt"]
        high_failures = conn.execute(
            "SELECT COUNT(*) AS cnt FROM webhooks WHERE failure_count > 5"
        ).fetchone()["cnt"]
    return {
        "total_webhooks": int(total),
        "active_webhooks": int(active),
        "deactivated_webhooks": int(deactivated),
        "high_failure_webhooks": int(high_failures),
    }


def notify_user_webhook_deactivated(user_id: str, webhook_id: str, url: str) -> None:
    """Best-effort email notification when webhook is auto-deactivated."""
    import os
    import smtplib
    from email.mime.text import MIMEText

    user = get_user_by_id(user_id)
    if not user or not user.get("email"):
        return

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    if not smtp_host:
        return

    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@reportagent.local")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes")

    body = (
        f"Your ReportAgent webhook was automatically deactivated after repeated delivery failures.\n\n"
        f"Webhook ID: {webhook_id}\n"
        f"URL: {url}\n\n"
        f"Re-activate via PUT /api/webhooks/{webhook_id} or POST /api/webhooks/{webhook_id}/reactivate"
    )
    msg = MIMEText(body)
    msg["Subject"] = "ReportAgent webhook deactivated"
    msg["From"] = smtp_from
    msg["To"] = user["email"]

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            if use_tls:
                server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.send_message(msg)
    except Exception:
        pass
