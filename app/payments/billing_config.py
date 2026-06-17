"""Billing / Stripe feature flags from environment."""

from __future__ import annotations

import os


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def billing_enabled() -> bool:
    """When false: no report limits, checkout disabled (testing / maintenance)."""
    return _env_bool("BILLING_ENABLED", default=True)


def stripe_checkout_enabled() -> bool:
    """Stripe checkout requires billing and a configured secret key."""
    if not billing_enabled():
        return False
    return bool(os.getenv("STRIPE_SECRET_KEY", "").strip())
