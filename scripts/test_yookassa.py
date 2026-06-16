#!/usr/bin/env python3
"""Smoke-test YooKassa integration endpoints (create/status/webhook signature)."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.is_file():
            load_dotenv(env_path)
    except ImportError:
        pass


def _sign_payload(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Test ReportAgent YooKassa integration")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--api-key", default="", help="User API key (X-API-Key)")
    parser.add_argument(
        "--plan-type",
        default="premium_monthly",
        choices=["premium_monthly", "premium_yearly", "enterprise"],
    )
    parser.add_argument("--skip-create", action="store_true")
    parser.add_argument("--payment-id", default="", help="Existing payment id for status check")
    parser.add_argument("--test-webhook", action="store_true", help="POST synthetic webhook")
    args = parser.parse_args()

    _load_env()
    base = args.base_url.rstrip("/")

    api_key = args.api_key.strip()
    if not api_key:
        print("ERROR: provide --api-key (from POST /api/keys/generate)")
        return 1

    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}
    payment_id = args.payment_id.strip()

    with httpx.Client(timeout=30.0) as client:
        if not args.skip_create:
            print(f"1) POST /api/payments/yookassa/create plan={args.plan_type}")
            resp = client.post(
                f"{base}/api/payments/yookassa/create",
                headers=headers,
                json={"plan_type": args.plan_type},
            )
            print(f"   HTTP {resp.status_code}")
            if resp.status_code not in (200, 201):
                print(resp.text)
                return 1
            payload = resp.json()
            payment_id = payload.get("payment_id", "")
            print(f"   payment_id={payment_id}")
            print(f"   confirmation_url={payload.get('confirmation_url')}")

        if payment_id:
            print(f"2) GET /api/payments/yookassa/status/{payment_id}")
            resp = client.get(f"{base}/api/payments/yookassa/status/{payment_id}", headers=headers)
            print(f"   HTTP {resp.status_code}")
            print(f"   body={resp.text[:500]}")

        if args.test_webhook:
            secret = os.getenv("YOOKASSA_SECRET_KEY", "").strip()
            if not secret:
                print("ERROR: YOOKASSA_SECRET_KEY not set for webhook signature test")
                return 1

            webhook_body = {
                "type": "notification",
                "event": "payment.succeeded",
                "object": {
                    "id": payment_id or "test-payment-id",
                    "status": "succeeded",
                    "amount": {"value": "19.90", "currency": "RUB"},
                    "metadata": {"user_id": "test-user", "plan_type": args.plan_type},
                    "payment_method": {"type": "bank_card"},
                },
            }
            raw = json.dumps(webhook_body, ensure_ascii=False).encode("utf-8")
            signature = _sign_payload(secret, raw)

            print("3) POST /webhooks/yookassa (signed)")
            resp = client.post(
                f"{base}/webhooks/yookassa",
                content=raw,
                headers={
                    "Content-Type": "application/json",
                    "Content-Signature": f"sha256={signature}",
                },
            )
            print(f"   HTTP {resp.status_code}")
            print(f"   body={resp.text[:300]}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
