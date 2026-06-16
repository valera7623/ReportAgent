#!/usr/bin/env python3
"""Smoke-test Stripe payments integration (test mode).

Usage:
  export STRIPE_SECRET_KEY=sk_test_...
  export STRIPE_WEBHOOK_SECRET=whsec_...
  python scripts/test_payments.py --base-url http://localhost:8000 --api-key YOUR_KEY

Creates a checkout session and prints webhook simulation instructions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid

import httpx

try:
    import stripe
except ImportError:
    print("Install dependencies: pip install stripe httpx", file=sys.stderr)
    sys.exit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Stripe payments flow")
    parser.add_argument("--base-url", default=os.getenv("REPORTAGENT_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.getenv("TEST_API_KEY", ""))
    parser.add_argument("--price-id", default=os.getenv("STRIPE_PRICE_ID_MONTHLY", ""))
    args = parser.parse_args()

    if not args.api_key:
        print("Provide --api-key or TEST_API_KEY", file=sys.stderr)
        return 1

    base = args.base_url.rstrip("/")
    headers = {"X-API-Key": args.api_key, "Content-Type": "application/json"}

    with httpx.Client(timeout=30.0) as client:
        prices = client.get(f"{base}/api/payments/prices").json()
        print("Prices:", json.dumps(prices, indent=2))

        sub_before = client.get(f"{base}/api/payments/subscription", headers=headers).json()
        print("Subscription before:", json.dumps(sub_before, indent=2))

        price_id = args.price_id or (prices.get("prices") or [{}])[0].get("id")
        if not price_id:
            print("No price_id configured", file=sys.stderr)
            return 1

        checkout = client.post(
            f"{base}/api/payments/create-checkout",
            headers=headers,
            json={
                "price_id": price_id,
                "success_url": f"{base}/success?session_id={{CHECKOUT_SESSION_ID}}",
                "cancel_url": f"{base}/cancel",
            },
        )
        if checkout.status_code >= 400:
            print("Checkout failed:", checkout.text, file=sys.stderr)
            return 1
        data = checkout.json()
        print("Checkout session:", json.dumps(data, indent=2))
        print("\nOpen URL in browser to complete test payment (card 4242 4242 4242 4242).")

    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if secret and os.getenv("STRIPE_SECRET_KEY"):
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
        print("\nWebhook: use Stripe CLI:")
        print(f"  stripe listen --forward-to {base}/webhooks/stripe")
        print("  stripe trigger checkout.session.completed")
    else:
        print("\nSet STRIPE_WEBHOOK_SECRET to test webhook signature locally.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
