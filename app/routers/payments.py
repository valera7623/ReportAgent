"""Stripe payments API endpoints."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.admin.dependency import admin_required
from app.db.database import get_connection, get_user_by_id
from app.payments import stripe_client
from app.payments.billing_config import billing_enabled, stripe_checkout_enabled
from app.payments.models import (
    AdminRefundResponse,
    AdminRevenueResponse,
    AdminSubscriptionsResponse,
    BillingConfigResponse,
    CancelSubscriptionResponse,
    CreateCheckoutRequest,
    CreateCheckoutResponse,
    PriceItem,
    PricesResponse,
    SubscriptionResponse,
)
from app.payments.stripe_client import StripeClientError
from app.payments.usage_tracker import (
    FREEMIUM_REPORTS_LIMIT,
    get_stripe_customer_id,
    get_subscription_api_response,
    plan_type_from_price_id,
)
from app.utils.logger import get_logger

logger = get_logger("payments_router", "log_payment_stripe.log")

router = APIRouter(prefix="/api/payments", tags=["Payments"])
admin_router = APIRouter(prefix="/admin/payments", tags=["Admin Payments"])


def _env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _default_success_url() -> str:
    return _env_str("STRIPE_SUCCESS_URL", "https://localhost/success?session_id={CHECKOUT_SESSION_ID}")


def _default_cancel_url() -> str:
    return _env_str("STRIPE_CANCEL_URL", "https://localhost/cancel")


def _price_catalog() -> list[tuple[str, str, str]]:
    """(price_id, display_name, plan_hint) from env."""
    return [
        (_env_str("STRIPE_PRICE_ID_MONTHLY"), "Monthly", "premium_monthly"),
        (_env_str("STRIPE_PRICE_ID_YEARLY"), "Yearly", "premium_yearly"),
        (_env_str("STRIPE_PRICE_ID_PAYG"), "Pay as you go", "enterprise"),
    ]


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return user_id


def _user_email(user_id: str) -> str:
    user = get_user_by_id(user_id)
    if not user or not user.get("email"):
        raise HTTPException(status_code=400, detail="User email is required for checkout")
    return str(user["email"])


@router.get("/config", response_model=BillingConfigResponse)
async def billing_config() -> BillingConfigResponse:
    """Public billing feature flags for the SPA."""
    return BillingConfigResponse(
        billing_enabled=billing_enabled(),
        stripe_enabled=stripe_checkout_enabled(),
    )


@router.get("/prices", response_model=PricesResponse)
async def list_prices() -> PricesResponse:
    """Public list of configured Stripe prices."""
    if not stripe_checkout_enabled():
        return PricesResponse(prices=[])
    items: list[PriceItem] = []
    for price_id, name, plan_type in _price_catalog():
        if not price_id:
            continue
        amount: int | None = None
        currency = "usd"
        interval: str | None = None
        try:
            price = stripe_client.retrieve_price(price_id)
            amount = int(price.get("unit_amount") or 0)
            currency = str(price.get("currency") or "usd")
            recurring = price.get("recurring") or {}
            interval = recurring.get("interval") if isinstance(recurring, dict) else None
        except StripeClientError:
            logger.debug("Could not fetch Stripe price %s from API", price_id)
        items.append(
            PriceItem(
                id=price_id,
                name=name,
                amount=amount,
                currency=currency,
                plan_type=plan_type,
                interval=interval,
            )
        )
    return PricesResponse(prices=items)


@router.post("/create-checkout", response_model=CreateCheckoutResponse)
async def create_checkout(request: Request, body: CreateCheckoutRequest) -> CreateCheckoutResponse:
    """Create Stripe Checkout session for authenticated user."""
    if not stripe_checkout_enabled():
        raise HTTPException(status_code=403, detail="Оплата Stripe временно отключена")
    user_id = _require_user_id(request)
    email = _user_email(user_id)

    success_url = body.success_url or _default_success_url()
    cancel_url = body.cancel_url or _default_cancel_url()
    plan_type = plan_type_from_price_id(body.price_id)
    mode = "subscription"
    payg_id = _env_str("STRIPE_PRICE_ID_PAYG")
    if body.price_id == payg_id and payg_id:
        mode = "payment"

    metadata = {"user_id": user_id, "plan_type": plan_type, "price_id": body.price_id}

    customer_id = get_stripe_customer_id(user_id)
    try:
        if not customer_id:
            customer_id = stripe_client.create_customer(email=email, metadata={"user_id": user_id})
            with get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO subscriptions (id, user_id, plan_type, status, monthly_reports_limit, stripe_customer_id, payment_provider)
                    VALUES (?, ?, 'freemium', 'active', ?, ?, 'stripe')
                    ON CONFLICT(user_id) DO UPDATE SET stripe_customer_id = excluded.stripe_customer_id
                    """,
                    (str(uuid.uuid4()), user_id, FREEMIUM_REPORTS_LIMIT, customer_id),
                )
        session = stripe_client.create_checkout_session(
            customer_id=customer_id,
            price_id=body.price_id,
            success_url=success_url,
            cancel_url=cancel_url,
            mode=mode,
            metadata=metadata,
        )
    except StripeClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return CreateCheckoutResponse(**session)


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(request: Request) -> SubscriptionResponse:
    """Current user subscription status (Stripe-primary)."""
    user_id = _require_user_id(request)
    data = get_subscription_api_response(user_id)
    return SubscriptionResponse(**data)


@router.post("/cancel-subscription", response_model=CancelSubscriptionResponse)
async def cancel_subscription_endpoint(request: Request) -> CancelSubscriptionResponse:
    """Cancel Stripe subscription or end YooKassa paid period early."""
    from app.payments.usage_tracker import cancel_subscription as local_cancel

    user_id = _require_user_id(request)
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT stripe_subscription_id, period_end, expires_at, payment_provider, yookassa_payment_id
            FROM subscriptions WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No subscription found")

    provider = (row["payment_provider"] or "").lower()
    if row["stripe_subscription_id"]:
        sub_id = str(row["stripe_subscription_id"])
        try:
            stripe_client.cancel_subscription(sub_id, at_period_end=True)
            sub_data = stripe_client.get_subscription(sub_id)
        except StripeClientError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        period_end = sub_data.get("current_period_end")
        effective = None
        if period_end:
            effective = datetime.fromtimestamp(int(period_end), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            effective = str(row["period_end"] or row["expires_at"] or "")

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE subscriptions
                SET status = 'canceled', expires_at = ?, updated_at = datetime('now')
                WHERE user_id = ?
                """,
                (effective, user_id),
            )
        return CancelSubscriptionResponse(
            status="canceled",
            effective_date=effective,
            payment_provider="stripe",
        )

    if provider == "yookassa" or row["yookassa_payment_id"]:
        effective = str(row["expires_at"] or row["period_end"] or "")
        local_cancel(user_id=user_id)
        return CancelSubscriptionResponse(
            status="canceled",
            effective_date=effective or None,
            payment_provider="yookassa",
        )

    raise HTTPException(status_code=404, detail="No active paid subscription to cancel")


# --- Admin ---


@admin_router.get("/subscriptions", response_model=AdminSubscriptionsResponse, dependencies=[Depends(admin_required)])
async def admin_list_subscriptions(
    status_filter: str | None = Query(default=None),
) -> AdminSubscriptionsResponse:
    with get_connection() as conn:
        if status_filter:
            rows = conn.execute(
                """
                SELECT id, user_id, plan_type, status, monthly_reports_limit, used_reports,
                       period_start, period_end, expires_at, stripe_customer_id, stripe_subscription_id,
                       payment_provider, created_at, updated_at
                FROM subscriptions
                WHERE status = ?
                ORDER BY datetime(created_at) DESC
                LIMIT 500
                """,
                (status_filter,),
            ).fetchall()
            total_row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM subscriptions WHERE status = ?",
                (status_filter,),
            ).fetchone()
        else:
            rows = conn.execute(
                """
                SELECT id, user_id, plan_type, status, monthly_reports_limit, used_reports,
                       period_start, period_end, expires_at, stripe_customer_id, stripe_subscription_id,
                       payment_provider, created_at, updated_at
                FROM subscriptions
                ORDER BY datetime(created_at) DESC
                LIMIT 500
                """
            ).fetchall()
            total_row = conn.execute("SELECT COUNT(*) AS cnt FROM subscriptions").fetchone()
    subs = [dict(r) for r in rows]
    return AdminSubscriptionsResponse(
        subscriptions=subs,
        total=int(total_row["cnt"]) if total_row else len(subs),
        status_filter=status_filter,
    )


@admin_router.get("/revenue", response_model=AdminRevenueResponse, dependencies=[Depends(admin_required)])
async def admin_revenue(
    period: str = Query(default="month", pattern="^(month|year)$"),
) -> AdminRevenueResponse:
    if period == "year":
        since = "datetime('now', '-1 year')"
    else:
        since = "datetime('now', '-1 month')"

    with get_connection() as conn:
        row = conn.execute(
            f"""
            SELECT COALESCE(SUM(amount), 0) AS total,
                   COUNT(*) AS cnt,
                   COALESCE(MAX(currency), 'usd') AS currency
            FROM payments
            WHERE status = 'succeeded'
              AND provider = 'stripe'
              AND datetime(created_at) >= {since}
            """
        ).fetchone()
        mrr_row = conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS mrr
            FROM payments
            WHERE status = 'succeeded'
              AND provider = 'stripe'
              AND datetime(created_at) >= datetime('now', '-1 month')
              AND description LIKE '%subscription%'
            """
        ).fetchone()

    return AdminRevenueResponse(
        period=period,
        currency=str(row["currency"] if row else "usd"),
        total_amount_cents=int(row["total"]) if row else 0,
        payment_count=int(row["cnt"]) if row else 0,
        mrr_cents=int(mrr_row["mrr"]) if mrr_row else 0,
    )


@admin_router.post("/refund/{payment_id}", response_model=AdminRefundResponse, dependencies=[Depends(admin_required)])
async def admin_refund(payment_id: str) -> AdminRefundResponse:
    from app.payments.usage_tracker import downgrade_after_refund

    with get_connection() as conn:
        row = conn.execute(
            "SELECT payment_id, user_id, stripe_payment_intent_id, amount, status, provider FROM payments WHERE payment_id = ?",
            (payment_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Payment not found")
    if (row["status"] or "").lower() != "succeeded":
        raise HTTPException(status_code=400, detail="Refund allowed only for succeeded payments")
    pi = row["stripe_payment_intent_id"]
    if not pi:
        raise HTTPException(status_code=400, detail="Payment has no Stripe payment intent")

    try:
        refund = stripe_client.create_refund(
            payment_intent_id=str(pi),
            amount_cents=int(row["amount"]),
        )
    except StripeClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    downgrade_after_refund(user_id=str(row["user_id"]), payment_id=payment_id)

    return AdminRefundResponse(payment_id=payment_id, refund=refund)
