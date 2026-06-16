"""Persist Stripe payment rows in SQLite."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.db.database import get_connection


def record_stripe_payment(
    *,
    payment_id: str,
    user_id: str,
    amount_cents: int,
    currency: str,
    status: str,
    description: str,
    payment_intent_id: str | None = None,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO payments
                (payment_id, user_id, amount, currency, status, description, provider,
                 stripe_payment_intent_id, stripe_checkout_session_id, created_at, captured_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, 'stripe', ?, ?, ?, ?, ?)
            ON CONFLICT(payment_id) DO UPDATE SET
                status = excluded.status,
                captured_at = excluded.captured_at,
                metadata_json = excluded.metadata_json
            """,
            (
                payment_id,
                user_id,
                amount_cents,
                currency,
                status,
                description,
                payment_intent_id,
                session_id,
                now,
                now if status == "succeeded" else None,
                json.dumps(metadata or {}),
            ),
        )
