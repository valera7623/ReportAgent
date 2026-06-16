"""Stripe API client with optional in-memory cache fallback (self-healing)."""

from __future__ import annotations

import os
import time
from typing import Any

import stripe

from app.utils.logger import get_logger

logger = get_logger("stripe_client", "log_payment_stripe.log")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "").strip()

if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

_subscription_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 300.0


class StripeClientError(Exception):
    """Stripe API or configuration error."""


def _require_configured() -> None:
    if not STRIPE_SECRET_KEY:
        raise StripeClientError("STRIPE_SECRET_KEY is not configured")


def create_customer(*, email: str, metadata: dict[str, str] | None = None) -> str:
    """Create Stripe Customer and return customer id."""
    _require_configured()
    try:
        customer = stripe.Customer.create(email=email, metadata=metadata or {})
        return str(customer.id)
    except stripe.StripeError as exc:
        logger.warning("Stripe create_customer failed: %s", exc.user_message or str(exc))
        raise StripeClientError("Failed to create Stripe customer") from exc


def create_checkout_session(
    *,
    customer_id: str,
    price_id: str,
    success_url: str,
    cancel_url: str,
    mode: str = "subscription",
    metadata: dict[str, str] | None = None,
) -> dict[str, str]:
    """Create Checkout Session; returns session_id and url."""
    _require_configured()
    try:
        session = stripe.checkout.Session.create(
            customer=customer_id,
            mode=mode,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata or {},
            subscription_data={"metadata": metadata or {}} if mode == "subscription" else None,
        )
        return {"session_id": str(session.id), "url": str(session.url)}
    except stripe.StripeError as exc:
        logger.warning("Stripe checkout session failed: %s", exc.user_message or str(exc))
        raise StripeClientError("Failed to create checkout session") from exc


def get_subscription(subscription_id: str) -> dict[str, Any]:
    """Retrieve subscription; on API failure return cached snapshot if available."""
    _require_configured()
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        payload = dict(sub)
        _subscription_cache[subscription_id] = (time.time(), payload)
        return payload
    except stripe.StripeError as exc:
        cached = _subscription_cache.get(subscription_id)
        if cached and (time.time() - cached[0]) < _CACHE_TTL_SECONDS:
            logger.warning(
                "Stripe get_subscription failed; using cache for %s: %s",
                subscription_id,
                exc.user_message or str(exc),
            )
            return cached[1]
        raise StripeClientError("Failed to retrieve subscription") from exc


def cancel_subscription(subscription_id: str, *, at_period_end: bool = True) -> bool:
    """Cancel Stripe subscription (default: at period end)."""
    _require_configured()
    try:
        if at_period_end:
            stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
        else:
            stripe.Subscription.delete(subscription_id)
        return True
    except stripe.StripeError as exc:
        logger.warning("Stripe cancel_subscription failed: %s", exc.user_message or str(exc))
        raise StripeClientError("Failed to cancel subscription") from exc


def retrieve_price(price_id: str) -> dict[str, Any]:
    """Retrieve Stripe Price object."""
    _require_configured()
    try:
        price = stripe.Price.retrieve(price_id)
        return dict(price)
    except stripe.StripeError as exc:
        raise StripeClientError(f"Failed to retrieve price {price_id}") from exc


def create_refund(*, payment_intent_id: str, amount_cents: int | None = None) -> dict[str, Any]:
    """Create refund for a payment intent."""
    _require_configured()
    try:
        params: dict[str, Any] = {"payment_intent": payment_intent_id}
        if amount_cents is not None:
            params["amount"] = amount_cents
        refund = stripe.Refund.create(**params)
        return dict(refund)
    except stripe.StripeError as exc:
        raise StripeClientError("Failed to create refund") from exc


def construct_webhook_event(payload: bytes, sig_header: str, secret: str) -> stripe.Event:
    """Verify webhook signature and return event."""
    return stripe.Webhook.construct_event(payload, sig_header, secret)
