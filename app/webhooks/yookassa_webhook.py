"""YooKassa webhook handler.

Endpoint:
  POST /webhooks/yookassa

Requirements:
 - No authentication middleware (see app/middleware/auth.py exemption).
 - Validates webhook signature; invalid signatures return 401.
 - Updates local payments/subscriptions and sends Telegram notifications.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.payments.usage_tracker import activate_subscription, cancel_subscription
from app.payments.yookassa_client import YooKassaClient, YooKassaClientError
from app.db.database import get_connection
from app.utils.logger import get_logger
from app.utils.metrics import record_yookassa_payment, refresh_active_subscriptions_gauge


logger = get_logger("yookassa_webhook", "log_payment_yookassa.log")

router = APIRouter(prefix="/webhooks", tags=["YooKassa Webhooks"])


def _env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


YOOKASSA_SECRET_KEY = _env_str("YOOKASSA_SECRET_KEY")


def _amount_to_cents(amount_value: str | None) -> int:
    if not amount_value:
        return 0
    # YooKassa amount.value is typically a string like "199.00".
    return int((Decimal(str(amount_value)) * 100).quantize(Decimal("1")))


def _get_signature_header(request: Request) -> str:
    # Common header name used by YooKassa webhook signature examples.
    # It may come as: "sha256=<hex_digest>"
    return request.headers.get("Content-Signature") or request.headers.get("X-Content-Signature") or ""


def _verify_signature(raw_body: bytes, signature_header: str) -> bool:
    if not YOOKASSA_SECRET_KEY:
        return False

    sig = signature_header.strip()
    if sig.startswith("sha256="):
        sig = sig.replace("sha256=", "", 1)

    # If YooKassa sends a different format (base64), this will not match.
    computed = hmac.new(YOOKASSA_SECRET_KEY.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, sig)


def _send_telegram_payment_alert(*, text: str) -> None:
    # Reuse same Telegram setup as other alerts.
    if os.getenv("ALERTS_ENABLED", "true").lower() not in ("1", "true", "yes"):
        return
    token = _env_str("TELEGRAM_BOT_TOKEN")
    chat_id = _env_str("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return

    import urllib.request
    import urllib.error

    payload = json.dumps(
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    ).encode()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            _ = resp.read()
    except (urllib.error.URLError, TimeoutError):
        # Avoid failing webhook due to Telegram issues.
        return


def _payment_method_type(payment_method: dict[str, Any] | None) -> str | None:
    if not payment_method:
        return None
    t = payment_method.get("type")
    if isinstance(t, str):
        return t
    return None


@router.post("/yookassa", response_class=JSONResponse)
async def yookassa_webhook(request: Request) -> JSONResponse:
    raw_body = await request.body()
    signature_header = _get_signature_header(request)

    if not _verify_signature(raw_body, signature_header):
        logger.warning("YooKassa webhook invalid signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = str(payload.get("event") or "")
    payment = payload.get("object") or {}
    payment_id = str(payment.get("id") or "")
    yookassa_status = str(payment.get("status") or "").lower()

    if not payment_id or "payment." not in event:
        return JSONResponse({"status": "ok"})

    metadata = payment.get("metadata") or {}
    user_id = metadata.get("user_id")
    plan_type = metadata.get("plan_type")

    if not user_id:
        with get_connection() as conn:
            existing = conn.execute(
                "SELECT user_id, metadata_json FROM payments WHERE payment_id = ?",
                (payment_id,),
            ).fetchone()
        if existing:
            user_id = existing["user_id"]
            if not plan_type and existing["metadata_json"]:
                try:
                    stored_meta = json.loads(existing["metadata_json"])
                    plan_type = stored_meta.get("plan_type")
                except json.JSONDecodeError:
                    pass

    amount_value = payment.get("amount", {}).get("value")
    currency = payment.get("amount", {}).get("currency") or "RUB"
    amount_cents = _amount_to_cents(amount_value)
    description = payment.get("description")
    payment_method = payment.get("payment_method")
    payment_method_type = _payment_method_type(payment_method)
    created_at = payment.get("created_at")
    captured_at = None

    if not user_id:
        logger.warning("YooKassa webhook missing user_id for payment %s", payment_id)
        return JSONResponse({"status": "ok"})

    try:
        if event == "payment.succeeded" or yookassa_status == "succeeded":
            captured_at = datetime.now(timezone.utc).isoformat()

            with get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO payments
                        (payment_id, user_id, amount, currency, status, description, payment_method, captured_at, metadata_json)
                    VALUES (?, ?, ?, ?, 'succeeded', ?, ?, ?, ?)
                    ON CONFLICT(payment_id) DO UPDATE SET
                        status = 'succeeded',
                        amount = excluded.amount,
                        currency = excluded.currency,
                        description = excluded.description,
                        payment_method = excluded.payment_method,
                        captured_at = COALESCE(excluded.captured_at, payments.captured_at),
                        metadata_json = COALESCE(excluded.metadata_json, payments.metadata_json)
                    """,
                    (
                        payment_id,
                        user_id,
                        amount_cents,
                        currency,
                        (description[:256] if isinstance(description, str) else None),
                        payment_method_type,
                        captured_at,
                        json.dumps(metadata, ensure_ascii=False),
                    ),
                )

            if user_id and plan_type:
                activate_subscription(
                    user_id=str(user_id),
                    plan_type=str(plan_type),  # type: ignore[arg-type]
                    yookassa_payment_id=payment_id,
                    yookassa_payment_method=str(payment_method_type) if payment_method_type else None,
                )

            record_yookassa_payment(status="succeeded", amount_rub=amount_cents / 100)
            refresh_active_subscriptions_gauge()

            if user_id and plan_type:
                amount_rub = f"{amount_cents/100:.2f}".replace(".", ",")
                text = (
                    "<b>ReportAgent · YooKassa payment succeeded</b>\n"
                    f"Plan: <b>{plan_type}</b>\n"
                    f"User: <code>{str(user_id)}</code>\n"
                    f"Amount: <b>{amount_rub} RUB</b>\n"
                    f"Payment: <code>{payment_id}</code>\n"
                )
                _send_telegram_payment_alert(text=text)

        elif event == "payment.waiting_for_capture" or yookassa_status == "waiting_for_capture":
            record_yookassa_payment(status="waiting_for_capture", amount_rub=amount_cents / 100)
            with get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO payments
                        (payment_id, user_id, amount, currency, status, description, payment_method, captured_at, metadata_json)
                    VALUES (?, ?, ?, ?, 'waiting_for_capture', ?, ?, NULL, ?)
                    ON CONFLICT(payment_id) DO UPDATE SET
                        status = 'waiting_for_capture',
                        amount = excluded.amount,
                        currency = excluded.currency,
                        description = excluded.description,
                        payment_method = excluded.payment_method,
                        metadata_json = COALESCE(excluded.metadata_json, payments.metadata_json)
                    """,
                    (
                        payment_id,
                        user_id,
                        amount_cents,
                        currency,
                        (description[:256] if isinstance(description, str) else None),
                        payment_method_type,
                        json.dumps(metadata, ensure_ascii=False),
                    ),
                )

            # Optionally auto-capture to transition to succeeded.
            if os.getenv("YOOKASSA_AUTO_CAPTURE_ON_WAITING", "true").lower() in ("1", "true", "yes"):
                try:
                    client = YooKassaClient(
                        shop_id=os.getenv("YOOKASSA_SHOP_ID", ""),
                        secret_key=os.getenv("YOOKASSA_SECRET_KEY", ""),
                        api_url=os.getenv("YOOKASSA_API_URL"),
                    )
                    await client.capture_payment(payment_id)
                except YooKassaClientError as exc:
                    logger.warning("Auto capture failed (ignored): %s", exc)

        elif event == "payment.canceled" or yookassa_status == "canceled":
            record_yookassa_payment(status="canceled", amount_rub=amount_cents / 100)
            refresh_active_subscriptions_gauge()
            with get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO payments
                        (payment_id, user_id, amount, currency, status, description, payment_method, captured_at, metadata_json)
                    VALUES (?, ?, ?, ?, 'canceled', ?, ?, NULL, ?)
                    ON CONFLICT(payment_id) DO UPDATE SET
                        status = 'canceled',
                        amount = excluded.amount,
                        currency = excluded.currency,
                        description = excluded.description,
                        payment_method = excluded.payment_method,
                        metadata_json = COALESCE(excluded.metadata_json, payments.metadata_json)
                    """,
                    (
                        payment_id,
                        user_id,
                        amount_cents,
                        currency,
                        (description[:256] if isinstance(description, str) else None),
                        payment_method_type,
                        json.dumps(metadata, ensure_ascii=False),
                    ),
                )

            if user_id:
                cancel_subscription(user_id=str(user_id))

        else:
            logger.info("Ignoring YooKassa event=%s payment_id=%s status=%s", event, payment_id, yookassa_status)

    except Exception as exc:
        logger.exception("Failed to process YooKassa webhook: %s", exc)
        _send_telegram_payment_alert(text=f"<b>ReportAgent · YooKassa webhook error</b>\n<code>{payment_id}</code>\n{exc}")

    # YooKassa expects 200 (2xx) ASAP. Body is ignored.
    return JSONResponse({"status": "ok"})

