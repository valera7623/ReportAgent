"""Usage tracking for report generation limits.

Enforces monthly report limits from SQLite `subscriptions` for Stripe and YooKassa.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Literal

from fastapi import HTTPException

from app.config.output_formats import EXTERNAL_FORMATS
from app.db.database import get_connection
from app.payments.billing_config import billing_enabled

_TESTING_UNLIMITED = 999_999


REPORT_LIMIT_PLAN = Literal["freemium", "premium_monthly", "premium_yearly", "enterprise"]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


FREEMIUM_REPORTS_LIMIT = _env_int("FREEMIUM_REPORTS_LIMIT", 5)
PREMIUM_REPORTS_LIMIT = _env_int("PREMIUM_REPORTS_LIMIT", 100)
ENTERPRISE_REPORTS_LIMIT = _env_int("ENTERPRISE_REPORTS_LIMIT", 1000)


def _month_bounds(now: datetime) -> tuple[str, str]:
    """Return ISO timestamps for UTC month start and first moment of next month."""
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    # SQLite stores TIMESTAMP as string; ISO-8601 keeps correct lexicographic ordering.
    return month_start.strftime("%Y-%m-%dT%H:%M:%SZ"), next_month.strftime("%Y-%m-%dT%H:%M:%SZ")


def _plan_monthly_limit(plan_type: REPORT_LIMIT_PLAN) -> int:
    if plan_type == "freemium":
        return FREEMIUM_REPORTS_LIMIT
    if plan_type in ("premium_monthly", "premium_yearly"):
        return PREMIUM_REPORTS_LIMIT
    if plan_type == "enterprise":
        return ENTERPRISE_REPORTS_LIMIT
    raise ValueError(f"Unknown plan type: {plan_type}")


def _plan_expires_at(plan_type: REPORT_LIMIT_PLAN, now: datetime) -> datetime | None:
    # Without YooKassa recurring billing, we treat successful payment as “access until …”.
    # - premium_monthly: 30 days
    # - premium_yearly: 365 days
    # - enterprise: 30 days (mapped to monthly usage)
    if plan_type == "premium_monthly":
        return now.replace(tzinfo=timezone.utc) + timedelta(days=30)
    if plan_type == "premium_yearly":
        return now.replace(tzinfo=timezone.utc) + timedelta(days=365)
    if plan_type == "enterprise":
        return now.replace(tzinfo=timezone.utc) + timedelta(days=30)
    return None


@dataclass(frozen=True)
class ConsumedSlot:
    plan_type: REPORT_LIMIT_PLAN
    monthly_limit: int
    used_reports: int
    remaining_reports: int


def _format_access_allowed(plan_type: REPORT_LIMIT_PLAN, desired_output_format: str | None) -> None:
    if not desired_output_format:
        return
    fmt = desired_output_format.strip().lower()
    if fmt in EXTERNAL_FORMATS and plan_type != "enterprise":
        raise HTTPException(
            status_code=402,
            detail="Расширенные форматы (Notion / Google Slides) доступны на тарифе Enterprise.",
        )


def _coerce_plan_type(value: str) -> REPORT_LIMIT_PLAN:
    v = (value or "").strip().lower()
    if v in ("freemium", "premium_monthly", "premium_yearly", "enterprise"):
        return v  # type: ignore[return-value]
    raise HTTPException(status_code=400, detail=f"Unknown plan_type '{value}'")


def _normalize_plan_type(value: str) -> REPORT_LIMIT_PLAN:
    v = (value or "").strip().lower()
    if v in ("freemium", "premium_monthly", "premium_yearly", "enterprise"):
        return v  # type: ignore[return-value]
    return "freemium"


def get_remaining_reports(user_id: str) -> int:
    """Return remaining report slots for the current period."""
    return int(get_user_subscription(user_id)["remaining_reports"])


def check_report_limit(
    user_id: str,
    desired_output_format: str | None = None,
    *,
    slot_reserved: bool = False,
) -> bool:
    """Return True if user may generate a report."""
    if not billing_enabled():
        return bool(user_id)
    if not user_id:
        return False
    try:
        sub = get_user_subscription(user_id)
        used = int(sub["used_reports"])
        limit = int(sub["monthly_reports_limit"])
        if slot_reserved:
            if used > limit or not bool(sub.get("is_active", True)):
                return False
        elif used >= limit or not bool(sub.get("is_active", True)):
            return False
        plan = _normalize_plan_type(str(sub["plan_type"]))
        _format_access_allowed(plan, desired_output_format)
        return True
    except HTTPException:
        return False


def increment_report_usage(
    user_id: str,
    desired_output_format: str | None = None,
) -> ConsumedSlot:
    """Atomically consume one report slot (preferred at API layer)."""
    return consume_report_slot(user_id=user_id, desired_output_format=desired_output_format)


def _api_plan_label(plan_type: str) -> str:
    """Map internal plan types to API-facing labels."""
    if plan_type in ("premium_monthly", "premium_yearly"):
        return "premium"
    if plan_type == "enterprise":
        return "enterprise"
    return "freemium"


def get_subscription_api_response(user_id: str) -> dict[str, object]:
    """Stripe-style subscription payload for GET /api/payments/subscription."""
    if not billing_enabled():
        return {
            "plan_type": "freemium",
            "status": "testing",
            "reports_limit": _TESTING_UNLIMITED,
            "reports_used": 0,
            "reports_remaining": _TESTING_UNLIMITED,
            "current_period_end": None,
            "is_active": True,
            "payment_provider": "disabled",
            "stripe_subscription_id": None,
        }
    sub = get_user_subscription(user_id)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT stripe_subscription_id, payment_provider, period_end FROM subscriptions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    period_end = None
    if row and row["period_end"]:
        period_end = str(row["period_end"])
    elif sub.get("period_end"):
        period_end = str(sub["period_end"])
    if sub.get("expires_at"):
        period_end = str(sub["expires_at"])
    return {
        "plan_type": _api_plan_label(str(sub["plan_type"])),
        "status": str(sub["status"]),
        "reports_limit": int(sub["monthly_reports_limit"]),
        "reports_used": int(sub["used_reports"]),
        "reports_remaining": int(sub["remaining_reports"]),
        "current_period_end": period_end,
        "is_active": bool(sub["is_active"]),
        "payment_provider": (row["payment_provider"] if row else None) or "freemium",
        "stripe_subscription_id": row["stripe_subscription_id"] if row else None,
    }


def activate_stripe_subscription(
    *,
    user_id: str,
    plan_type: REPORT_LIMIT_PLAN,
    stripe_customer_id: str | None,
    stripe_subscription_id: str | None,
    current_period_start: str | None,
    current_period_end: str | None,
    status: str = "active",
) -> None:
    """Activate or update subscription from Stripe webhook events."""
    now = datetime.now(timezone.utc)
    period_start = current_period_start or _month_bounds(now)[0]
    period_end = current_period_end or _month_bounds(now)[1]
    expires_at = current_period_end
    monthly_limit = _plan_monthly_limit(plan_type)

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO subscriptions
                (id, user_id, plan_type, status, monthly_reports_limit, used_reports,
                 period_start, period_end, expires_at,
                 stripe_customer_id, stripe_subscription_id, payment_provider, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, 'stripe', datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                plan_type = excluded.plan_type,
                status = excluded.status,
                monthly_reports_limit = excluded.monthly_reports_limit,
                period_start = excluded.period_start,
                period_end = excluded.period_end,
                expires_at = excluded.expires_at,
                stripe_customer_id = COALESCE(excluded.stripe_customer_id, subscriptions.stripe_customer_id),
                stripe_subscription_id = COALESCE(excluded.stripe_subscription_id, subscriptions.stripe_subscription_id),
                payment_provider = 'stripe',
                updated_at = datetime('now')
            """,
            (
                str(uuid.uuid4()),
                user_id,
                plan_type,
                status,
                monthly_limit,
                period_start,
                period_end,
                expires_at,
                stripe_customer_id,
                stripe_subscription_id,
            ),
        )


def cancel_stripe_subscription(*, user_id: str, effective_date: str | None = None) -> None:
    """Mark subscription canceled locally after Stripe cancellation."""
    now = datetime.now(timezone.utc)
    effective = effective_date or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    period_start, period_end = _month_bounds(now)
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            UPDATE subscriptions
            SET status = 'canceled',
                expires_at = ?,
                plan_type = 'freemium',
                monthly_reports_limit = ?,
                used_reports = 0,
                period_start = ?,
                period_end = ?,
                stripe_subscription_id = NULL,
                payment_provider = 'freemium',
                updated_at = datetime('now')
            WHERE user_id = ?
            """,
            (effective, FREEMIUM_REPORTS_LIMIT, period_start, period_end, user_id),
        )


def get_stripe_customer_id(user_id: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT stripe_customer_id FROM subscriptions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    return str(row["stripe_customer_id"]) if row and row["stripe_customer_id"] else None


def plan_type_from_price_id(price_id: str) -> REPORT_LIMIT_PLAN:
    """Map configured Stripe price id to internal plan type."""
    monthly = os.getenv("STRIPE_PRICE_ID_MONTHLY", "").strip()
    yearly = os.getenv("STRIPE_PRICE_ID_YEARLY", "").strip()
    payg = os.getenv("STRIPE_PRICE_ID_PAYG", "").strip()
    enterprise = os.getenv("STRIPE_PRICE_ID_ENTERPRISE", "").strip() or payg
    if price_id == monthly:
        return "premium_monthly"
    if price_id == yearly:
        return "premium_yearly"
    if price_id == enterprise or price_id == payg:
        return "enterprise"
    return "premium_monthly"


def get_user_subscription(user_id: str) -> dict[str, object]:
    """Return current subscription snapshot for API/dashboard (read-only)."""
    now = datetime.now(timezone.utc)
    now_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    period_start, period_end = _month_bounds(now)

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT plan_type, status, monthly_reports_limit, used_reports,
                   period_start, period_end, expires_at
            FROM subscriptions
            WHERE user_id = ?
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

    if not row:
        limit = FREEMIUM_REPORTS_LIMIT
        return {
            "plan_type": "freemium",
            "status": "active",
            "is_active": True,
            "monthly_reports_limit": limit,
            "used_reports": 0,
            "remaining_reports": limit,
            "expires_at": None,
            "period_start": period_start,
            "period_end": period_end,
        }

    status = (row["status"] or "active").lower()
    expires_at = row["expires_at"]
    is_active = status == "active" and (expires_at is None or str(expires_at) >= now_iso)

    if is_active:
        plan_type = _normalize_plan_type(row["plan_type"])
        monthly_limit = int(row["monthly_reports_limit"])
        used_reports = int(row["used_reports"])
        row_period_start = row["period_start"]
        if not row_period_start or str(row_period_start)[:7] != period_start[:7]:
            used_reports = 0
        sub_status = status
        expires_value = str(expires_at) if expires_at else None
        period_start_value = str(row["period_start"]) if row["period_start"] else period_start
        period_end_value = str(row["period_end"]) if row["period_end"] else period_end
    else:
        plan_type = "freemium"
        monthly_limit = FREEMIUM_REPORTS_LIMIT
        used_reports = 0
        sub_status = "freemium"
        expires_value = None
        period_start_value = period_start
        period_end_value = period_end

    return {
        "plan_type": plan_type,
        "status": sub_status,
        "is_active": is_active,
        "monthly_reports_limit": monthly_limit,
        "used_reports": used_reports,
        "remaining_reports": max(0, monthly_limit - used_reports),
        "expires_at": expires_value,
        "period_start": period_start_value,
        "period_end": period_end_value,
    }


def get_active_subscription_plan(user_id: str) -> REPORT_LIMIT_PLAN:
    """Return plan type based on subscription status/expiration; falls back to freemium."""
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT plan_type, status, expires_at
            FROM subscriptions
            WHERE user_id = ?
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

    if not row:
        return "freemium"

    status = (row["status"] or "").lower()
    expires_at = row["expires_at"]
    active = status == "active" and (expires_at is None or str(expires_at) >= now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return _coerce_plan_type(row["plan_type"]) if active else "freemium"


def consume_report_slot(*, user_id: str, desired_output_format: str | None = None) -> ConsumedSlot:
    """Atomically consume 1 report usage slot for current UTC month."""
    if not user_id:
        raise HTTPException(status_code=401, detail="User is required")

    if not billing_enabled():
        return ConsumedSlot(
            plan_type="freemium",
            monthly_limit=_TESTING_UNLIMITED,
            used_reports=0,
            remaining_reports=_TESTING_UNLIMITED,
        )

    now = datetime.now(timezone.utc)
    period_start, period_end = _month_bounds(now)

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")

        row = conn.execute(
            """
            SELECT id, plan_type, status, monthly_reports_limit, used_reports, period_start, period_end, expires_at
            FROM subscriptions
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        if not row:
            plan_type: REPORT_LIMIT_PLAN = "freemium"
            monthly_limit = _plan_monthly_limit(plan_type)
            conn.execute(
                """
                INSERT INTO subscriptions
                    (id, user_id, plan_type, status, monthly_reports_limit, used_reports, period_start, period_end, expires_at)
                VALUES (?, ?, ?, 'active', ?, 0, ?, ?, NULL)
                """,
                (str(uuid.uuid4()), user_id, plan_type, monthly_limit, period_start, period_end),
            )
            used_reports = 0
            status = "active"
        else:
            plan_type = _coerce_plan_type(row["plan_type"])
            status = (row["status"] or "").lower()
            expires_at = row["expires_at"]

            is_active = status == "active" and (
                expires_at is None or str(expires_at) >= now.strftime("%Y-%m-%dT%H:%M:%SZ")
            )
            if not is_active:
                plan_type = "freemium"
                monthly_limit = _plan_monthly_limit(plan_type)
                used_reports = 0
                conn.execute(
                    """
                    UPDATE subscriptions
                    SET plan_type = ?,
                        status = 'active',
                        monthly_reports_limit = ?,
                        used_reports = 0,
                        period_start = ?,
                        period_end = ?,
                        expires_at = NULL,
                        yookassa_payment_id = NULL,
                        yookassa_payment_method = NULL
                    WHERE user_id = ?
                    """,
                    (plan_type, monthly_limit, period_start, period_end, user_id),
                )
            else:
                monthly_limit = int(row["monthly_reports_limit"])
                used_reports = int(row["used_reports"])

                # Reset usage counter if month changed.
                row_period_start = row["period_start"]
                if not row_period_start or str(row_period_start)[:7] != period_start[:7]:
                    conn.execute(
                        """
                        UPDATE subscriptions
                        SET used_reports = 0,
                            period_start = ?,
                            period_end = ?
                        WHERE user_id = ?
                        """,
                        (period_start, period_end, user_id),
                    )
                    used_reports = 0

        # Read after reset to avoid confusion if we updated in different branch.
        current = conn.execute(
            """
            SELECT plan_type, monthly_reports_limit, used_reports
            FROM subscriptions
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        plan_type = _coerce_plan_type(current["plan_type"])
        monthly_limit = int(current["monthly_reports_limit"])
        used_reports = int(current["used_reports"])

        _format_access_allowed(plan_type, desired_output_format)

        if used_reports >= monthly_limit:
            raise HTTPException(
                status_code=402,
                detail={
                    "message": "Лимит отчётов исчерпан. Оформите подписку.",
                    "upgrade_url": "/app#/pricing",
                    "code": "report_limit_exceeded",
                },
            )

        conn.execute(
            """
            UPDATE subscriptions
            SET used_reports = used_reports + 1
            WHERE user_id = ?
            """,
            (user_id,),
        )

        updated = conn.execute(
            """
            SELECT used_reports, monthly_reports_limit, plan_type
            FROM subscriptions
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        used_reports = int(updated["used_reports"])
        monthly_limit = int(updated["monthly_reports_limit"])
        plan_type = _coerce_plan_type(updated["plan_type"])

        return ConsumedSlot(
            plan_type=plan_type,
            monthly_limit=monthly_limit,
            used_reports=used_reports,
            remaining_reports=max(0, monthly_limit - used_reports),
        )


def activate_subscription(
    *,
    user_id: str,
    plan_type: REPORT_LIMIT_PLAN,
    yookassa_payment_id: str,
    yookassa_payment_method: str | None,
) -> None:
    """Activate (or replace) user subscription after successful payment."""
    now = datetime.now(timezone.utc)
    period_start, period_end = _month_bounds(now)
    expires_at_dt = _plan_expires_at(plan_type, now)
    expires_at = expires_at_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if expires_at_dt else None
    monthly_limit = _plan_monthly_limit(plan_type)

    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO subscriptions
                (id, user_id, plan_type, status, monthly_reports_limit, used_reports, period_start, period_end, expires_at, yookassa_payment_id, yookassa_payment_method)
            VALUES (?, ?, ?, 'active', ?, 0, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                plan_type = excluded.plan_type,
                status = 'active',
                monthly_reports_limit = excluded.monthly_reports_limit,
                used_reports = 0,
                period_start = excluded.period_start,
                period_end = excluded.period_end,
                expires_at = excluded.expires_at,
                yookassa_payment_id = excluded.yookassa_payment_id,
                yookassa_payment_method = excluded.yookassa_payment_method
            """,
            (
                str(uuid.uuid4()),
                user_id,
                plan_type,
                monthly_limit,
                period_start,
                period_end,
                expires_at,
                yookassa_payment_id,
                yookassa_payment_method,
            ),
        )


def cancel_subscription(*, user_id: str) -> None:
    """Cancel user subscription (set freemium-like limits by expiring current access)."""
    now = datetime.now(timezone.utc)
    expires_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    period_start, period_end = _month_bounds(now)
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            UPDATE subscriptions
            SET status = 'canceled',
                expires_at = ?,
                plan_type = 'freemium',
                monthly_reports_limit = ?,
                used_reports = 0,
                period_start = ?,
                period_end = ?,
                yookassa_payment_id = NULL,
                yookassa_payment_method = NULL,
                stripe_subscription_id = NULL
            WHERE user_id = ?
            """,
            (expires_at, FREEMIUM_REPORTS_LIMIT, period_start, period_end, user_id),
        )

