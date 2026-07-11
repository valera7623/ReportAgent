"""Stripe webhook handler — POST /webhooks/stripe (no API key auth)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

import stripe
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.payments import stripe_client
from app.payments.usage_tracker import (
    activate_stripe_subscription,
    cancel_stripe_subscription,
    plan_type_from_price_id,
)
from app.payments.payment_records import record_stripe_payment as _record_stripe_payment
from app.db.database import get_connection
from app.utils.logger import get_logger
from app.utils.metrics import (
    record_stripe_payment,
    refresh_active_subscriptions_gauge,
    update_mrr_gauge,
)

logger = get_logger("stripe_webhook", "log_payment_stripe.log")

router = APIRouter(prefix="/webhooks", tags=["Stripe Webhooks"])

WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()


def _send_telegram_payment_alert(*, text: str) -> None:
    if os.getenv("ALERTS_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return
    import urllib.error
    import urllib.parse
    import urllib.request

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text[:4000]}).encode()
    try:
        urllib.request.urlopen(url, data=data, timeout=10)
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.warning("Telegram alert failed: %s", exc)


def _ts_iso(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _metadata_user_id(metadata: dict[str, Any] | None) -> str | None:
    if not metadata:
        return None
    uid = metadata.get("user_id")
    return str(uid) if uid else None


def _handle_checkout_completed(session: dict[str, Any]) -> None:
    metadata = session.get("metadata") or {}
    user_id = _metadata_user_id(metadata)
    if not user_id:
        logger.warning("checkout.session.completed without user_id metadata")
        return

    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    price_id = metadata.get("price_id") or ""
    plan_type = metadata.get("plan_type") or plan_type_from_price_id(str(price_id))

    if subscription_id:
        sub = stripe_client.get_subscription(str(subscription_id))
        activate_stripe_subscription(
            user_id=user_id,
            plan_type=plan_type,  # type: ignore[arg-type]
            stripe_customer_id=str(customer_id) if customer_id else None,
            stripe_subscription_id=str(subscription_id),
            current_period_start=_ts_iso(sub.get("current_period_start")),
            current_period_end=_ts_iso(sub.get("current_period_end")),
            status=str(sub.get("status") or "active"),
        )
    else:
        # One-time payment (PAYG)
        activate_stripe_subscription(
            user_id=user_id,
            plan_type=plan_type,  # type: ignore[arg-type]
            stripe_customer_id=str(customer_id) if customer_id else None,
            stripe_subscription_id=None,
            current_period_start=_ts_iso(session.get("created")),
            current_period_end=None,
            status="active",
        )

    amount = int(session.get("amount_total") or 0)
    currency = str(session.get("currency") or "usd")
    payment_id = str(session.get("payment_intent") or session.get("id") or uuid.uuid4())
    _record_stripe_payment(
        payment_id=payment_id,
        user_id=user_id,
        amount_cents=amount,
        currency=currency,
        status="succeeded",
        description="Stripe checkout completed",
        payment_intent_id=str(session.get("payment_intent")) if session.get("payment_intent") else None,
        session_id=str(session.get("id")),
        metadata=metadata,
    )
    record_stripe_payment(status="succeeded", amount_cents=amount, currency=currency)
    refresh_active_subscriptions_gauge()
    _send_telegram_payment_alert(text=f"✅ Stripe payment succeeded for user {user_id[:8]}…")


def _sync_subscription_object(sub: dict[str, Any], *, user_id: str | None = None) -> None:
    uid = user_id or _metadata_user_id(sub.get("metadata"))
    if not uid:
        logger.warning("subscription event without user_id")
        return

    status = str(sub.get("status") or "active")
    items = (sub.get("items") or {}).get("data") or []
    price_id = ""
    if items:
        price = items[0].get("price") or {}
        price_id = str(price.get("id") or "")
    plan_type = plan_type_from_price_id(price_id) if price_id else "premium_monthly"

    if status in ("canceled", "unpaid", "incomplete_expired"):
        cancel_stripe_subscription(
            user_id=uid,
            effective_date=_ts_iso(sub.get("canceled_at") or sub.get("current_period_end")),
        )
        record_stripe_payment(status="canceled")
    else:
        activate_stripe_subscription(
            user_id=uid,
            plan_type=plan_type,  # type: ignore[arg-type]
            stripe_customer_id=str(sub.get("customer")) if sub.get("customer") else None,
            stripe_subscription_id=str(sub.get("id")),
            current_period_start=_ts_iso(sub.get("current_period_start")),
            current_period_end=_ts_iso(sub.get("current_period_end")),
            status=status,
        )
    refresh_active_subscriptions_gauge()


def _handle_invoice_payment(invoice: dict[str, Any], *, succeeded: bool) -> None:
    metadata = invoice.get("metadata") or {}
    user_id = _metadata_user_id(metadata)
    sub_details = invoice.get("subscription_details") or {}
    if not user_id and isinstance(sub_details, dict):
        user_id = _metadata_user_id(sub_details.get("metadata"))

    amount = int(invoice.get("amount_paid") or invoice.get("amount_due") or 0)
    currency = str(invoice.get("currency") or "usd")
    payment_intent = invoice.get("payment_intent")
    payment_id = str(payment_intent or invoice.get("id") or uuid.uuid4())

    if user_id:
        _record_stripe_payment(
            payment_id=payment_id,
            user_id=user_id,
            amount_cents=amount,
            currency=currency,
            status="succeeded" if succeeded else "failed",
            description="Stripe subscription invoice",
            payment_intent_id=str(payment_intent) if payment_intent else None,
            metadata=metadata,
        )

    if succeeded:
        record_stripe_payment(status="succeeded", amount_cents=amount, currency=currency)
        update_mrr_gauge(amount_cents=amount)
        if user_id:
            _send_telegram_payment_alert(text=f"✅ Stripe invoice paid for user {user_id[:8]}…")
    else:
        record_stripe_payment(status="failed", amount_cents=amount, currency=currency)
        if user_id:
            _send_telegram_payment_alert(text=f"⚠️ Stripe invoice payment failed for user {user_id[:8]}…")


def _claim_stripe_event(event_id: str, event_type: str) -> bool:
    """Return True if this event_id was newly claimed (not a replay)."""
    if not event_id:
        return True
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO stripe_webhook_events (event_id, event_type)
                VALUES (?, ?)
                """,
                (event_id, event_type),
            )
            return True
        except Exception:
            # UNIQUE constraint — already processed
            existing = conn.execute(
                "SELECT 1 FROM stripe_webhook_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if existing:
                return False
            raise


@router.post("/stripe")
async def stripe_webhook(request: Request) -> JSONResponse:
    """Stripe webhook endpoint (signature required)."""
    if not WEBHOOK_SECRET:
        logger.error("STRIPE_WEBHOOK_SECRET is not configured")
        raise HTTPException(status_code=401)

    payload = await request.body()
    sig = request.headers.get("Stripe-Signature") or ""
    try:
        event = stripe_client.construct_webhook_event(payload, sig, WEBHOOK_SECRET)
    except (stripe.SignatureVerificationError, ValueError):
        raise HTTPException(status_code=401) from None

    event_id = str(event.get("id") or "")
    event_type = event["type"]
    data_object = event["data"]["object"]

    if not _claim_stripe_event(event_id, event_type):
        logger.info("Ignoring duplicate Stripe event %s (%s)", event_id, event_type)
        return JSONResponse({"status": "ok", "duplicate": True})

    try:
        if event_type == "checkout.session.completed":
            _handle_checkout_completed(dict(data_object))
        elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
            _sync_subscription_object(dict(data_object))
        elif event_type == "customer.subscription.deleted":
            uid = _metadata_user_id(dict(data_object).get("metadata"))
            if uid:
                cancel_stripe_subscription(
                    user_id=uid,
                    effective_date=_ts_iso(dict(data_object).get("canceled_at")),
                )
                refresh_active_subscriptions_gauge()
        elif event_type == "invoice.payment_succeeded":
            _handle_invoice_payment(dict(data_object), succeeded=True)
        elif event_type == "invoice.payment_failed":
            _handle_invoice_payment(dict(data_object), succeeded=False)
    except Exception as exc:
        logger.exception("Stripe webhook handler error for %s: %s", event_type, exc)
        _send_telegram_payment_alert(text=f"❌ Stripe webhook error: {event_type}")
        # Allow Stripe to retry — remove claim so replay can reprocess.
        if event_id:
            try:
                with get_connection() as conn:
                    conn.execute(
                        "DELETE FROM stripe_webhook_events WHERE event_id = ?",
                        (event_id,),
                    )
            except Exception:
                logger.warning("Failed to release Stripe event claim %s", event_id)
        raise HTTPException(status_code=500, detail="Webhook processing failed") from exc

    return JSONResponse({"status": "ok"})
