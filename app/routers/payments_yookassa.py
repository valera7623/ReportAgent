"""Payments API for YooKassa (create/status + admin tools)."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.admin.dependency import admin_required
from app.db.database import get_connection
from app.payments.billing_config import billing_enabled
from app.payments.usage_tracker import activate_subscription, cancel_subscription, get_user_subscription
from app.payments.yookassa_client import YooKassaClient, YooKassaClientError
from app.utils.metrics import record_yookassa_payment, refresh_active_subscriptions_gauge
from app.payments.yookassa_models import (
    YooKassaCreatePaymentRequest,
    YooKassaCreatePaymentResponse,
    YooKassaPaymentStatusResponse,
    YooKassaPlanType,
    YooKassaSubscriptionResponse,
)


def _env_str(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


FREEMIUM_REPORTS_LIMIT = _env_int("FREEMIUM_REPORTS_LIMIT", 5)
PREMIUM_REPORTS_LIMIT = _env_int("PREMIUM_REPORTS_LIMIT", 100)
ENTERPRISE_REPORTS_LIMIT = _env_int("ENTERPRISE_REPORTS_LIMIT", 1000)

# Prices are expected in kopeks (cents) per env.example comments.
PRICE_PREMIUM_MONTHLY = _env_int("PRICE_PREMIUM_MONTHLY", 1990)
PRICE_PREMIUM_YEARLY = _env_int("PRICE_PREMIUM_YEARLY", 19900)
PRICE_ENTERPRISE = _env_int("PRICE_ENTERPRISE", 9990)


def _amount_value_to_rub(amount_value: str | None) -> float:
    if not amount_value:
        return 0.0
    return float(Decimal(str(amount_value)).quantize(Decimal("0.01")))


def _plan_amount_and_limit(plan_type: YooKassaPlanType) -> tuple[int, int]:
    if plan_type == YooKassaPlanType.premium_monthly:
        return PRICE_PREMIUM_MONTHLY, PREMIUM_REPORTS_LIMIT
    if plan_type == YooKassaPlanType.premium_yearly:
        return PRICE_PREMIUM_YEARLY, PREMIUM_REPORTS_LIMIT
    if plan_type == YooKassaPlanType.enterprise:
        return PRICE_ENTERPRISE, ENTERPRISE_REPORTS_LIMIT
    raise ValueError(f"Unknown plan_type: {plan_type}")


class AdminRefundResponse(BaseModel):
    payment_id: str
    refund: dict[str, Any]


router = APIRouter(prefix="/api/payments/yookassa", tags=["Payments (YooKassa)"])
admin_router = APIRouter(prefix="/admin/payments/yookassa", tags=["Admin Payments (YooKassa)"])


def _client() -> YooKassaClient:
    return YooKassaClient(
        shop_id=_env_str("YOOKASSA_SHOP_ID"),
        secret_key=_env_str("YOOKASSA_SECRET_KEY"),
        api_url=os.getenv("YOOKASSA_API_URL"),
    )


@router.post("/create", response_model=YooKassaCreatePaymentResponse, status_code=201)
async def yookassa_create_payment(
    request: Request,
    body: YooKassaCreatePaymentRequest,
) -> YooKassaCreatePaymentResponse:
    if not billing_enabled():
        raise HTTPException(status_code=403, detail="Оплата временно отключена")
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    return_url_success = _env_str("YOOKASSA_RETURN_URL_SUCCESS")

    amount_cents, _monthly_limit = _plan_amount_and_limit(body.plan_type)
    plan_type_value = body.plan_type.value

    description = f"ReportAgent: {plan_type_value} subscription"
    metadata = {"user_id": user_id, "plan_type": plan_type_value}

    try:
        client = _client()
        created = await client.create_payment(
            amount=amount_cents,
            currency="RUB",
            description=description,
            return_url=return_url_success,
            metadata=metadata,
            capture=True,
        )
    except YooKassaClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payment_id = created.payment_id
    confirmation_url = created.confirmation_url

    payments_metadata = json.dumps(metadata, ensure_ascii=False)

    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO payments
                (payment_id, user_id, amount, currency, status, description, payment_method, metadata_json)
            VALUES (?, ?, ?, 'RUB', 'pending', ?, NULL, ?)
            """,
            (payment_id, user_id, amount_cents, description[:256], payments_metadata),
        )

    return YooKassaCreatePaymentResponse(payment_id=payment_id, confirmation_url=confirmation_url)


@router.get("/subscription", response_model=YooKassaSubscriptionResponse)
async def yookassa_get_subscription(request: Request) -> YooKassaSubscriptionResponse:
    """Current user plan, usage limits and expiration."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    data = get_user_subscription(user_id)
    return YooKassaSubscriptionResponse(**data)


@router.get("/status/{payment_id}", response_model=YooKassaPaymentStatusResponse)
async def yookassa_check_status(
    request: Request,
    payment_id: str,
) -> YooKassaPaymentStatusResponse:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")

    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM payments WHERE payment_id = ? AND user_id = ?",
            (payment_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Payment not found")

        # Keep local metadata for later activation.
        metadata_json = row["metadata_json"]
        local_meta = json.loads(metadata_json) if metadata_json else {}

    try:
        client = _client()
        data = await client.get_payment(payment_id)
    except YooKassaClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    yookassa_status = str(data.get("status") or "").lower()
    status_map: dict[str, str] = {
        "pending": "pending",
        "waiting_for_capture": "waiting_for_capture",
        "succeeded": "succeeded",
        "canceled": "canceled",
        "cancelled": "canceled",
    }
    local_status = status_map.get(yookassa_status, yookassa_status or "pending")

    amount_value = data.get("amount", {}).get("value")
    currency = str(data.get("amount", {}).get("currency") or row["currency"] or "RUB")
    payment_method_type = data.get("payment_method", {}).get("type")
    captured_at = data.get("captured_at")
    description = data.get("description") or row["description"]

    # Merge metadata: prefer remote metadata if present.
    remote_meta = data.get("metadata") or {}
    meta = remote_meta if remote_meta else local_meta
    plan_type_value = (meta.get("plan_type") or "").strip()
    plan_type = plan_type_value if plan_type_value else None
    yookassa_payment_id = str(data.get("id") or payment_id)
    yookassa_payment_method = payment_method_type

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE payments
            SET status = ?,
                currency = ?,
                description = ?,
                payment_method = ?,
                captured_at = ?
            WHERE payment_id = ?
            """,
            (local_status, currency, description, payment_method_type, captured_at, payment_id),
        )

    # Activation logic is idempotent-ish thanks to subscriptions UNIQUE(user_id).
    if local_status == "succeeded" and plan_type in (
        "premium_monthly",
        "premium_yearly",
        "enterprise",
    ):
        activate_subscription(
            user_id=user_id,
            plan_type=plan_type,  # type: ignore[arg-type]
            yookassa_payment_id=yookassa_payment_id,
            yookassa_payment_method=str(yookassa_payment_method) if yookassa_payment_method else None,
        )
    elif local_status == "canceled":
        cancel_subscription(user_id=user_id)

    if local_status in ("succeeded", "waiting_for_capture", "canceled", "pending"):
        amount_rub = _amount_value_to_rub(str(amount_value) if amount_value is not None else None)
        record_yookassa_payment(
            status=local_status,
            amount_rub=amount_rub if local_status == "succeeded" else None,
        )
        refresh_active_subscriptions_gauge()

    return YooKassaPaymentStatusResponse(payment_id=payment_id, status=local_status)


# --- Admin endpoints ---


class AdminListPaymentsResponse(BaseModel):
    payments: list[dict[str, Any]]
    total: int
    status_filter: str | None = None


@admin_router.get("", response_model=AdminListPaymentsResponse, dependencies=[Depends(admin_required)])
async def admin_list_payments(
    request: Request,
    status_filter: str | None = Query(default=None, description="Filter by status"),
) -> AdminListPaymentsResponse:
    with get_connection() as conn:
        if status_filter:
            rows = conn.execute(
                """
                SELECT payment_id, user_id, amount, currency, status, description, payment_method, created_at, captured_at
                FROM payments
                WHERE status = ?
                ORDER BY datetime(created_at) DESC
                LIMIT 500
                """,
                (status_filter,),
            ).fetchall()
            total_row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM payments WHERE status = ?",
                (status_filter,),
            ).fetchone()
        else:
            rows = conn.execute(
                """
                SELECT payment_id, user_id, amount, currency, status, description, payment_method, created_at, captured_at
                FROM payments
                ORDER BY datetime(created_at) DESC
                LIMIT 500
                """,
            ).fetchall()
            total_row = conn.execute("SELECT COUNT(*) AS cnt FROM payments").fetchone()

    payments = [dict(r) for r in rows]
    total = int(total_row["cnt"]) if total_row else len(payments)
    return AdminListPaymentsResponse(payments=payments, total=total, status_filter=status_filter)


@admin_router.get("/{payment_id}", dependencies=[Depends(admin_required)])
async def admin_get_payment(payment_id: str) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM payments WHERE payment_id = ?", (payment_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Payment not found")
        payload = dict(row)
        metadata_json = payload.get("metadata_json")
        try:
            payload["metadata"] = json.loads(metadata_json) if metadata_json else {}
        except Exception:
            payload["metadata"] = {}
        payload.pop("metadata_json", None)
        return payload


@admin_router.post("/refund/{payment_id}", dependencies=[Depends(admin_required)], response_model=AdminRefundResponse)
async def admin_refund_payment(payment_id: str) -> AdminRefundResponse:
    from app.payments.usage_tracker import downgrade_after_refund

    with get_connection() as conn:
        row = conn.execute(
            "SELECT payment_id, user_id, amount, currency, status FROM payments WHERE payment_id = ?",
            (payment_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Payment not found")
        if (row["status"] or "").lower() != "succeeded":
            raise HTTPException(status_code=400, detail="Refund is allowed only for succeeded payments")
        amount_cents = int(row["amount"])
        user_id = str(row["user_id"])

    try:
        client = _client()
        refund = await client.refund_payment(payment_id, amount=amount_cents)
    except YooKassaClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    downgrade_after_refund(user_id=user_id, payment_id=payment_id)
    refresh_active_subscriptions_gauge()

    return AdminRefundResponse(payment_id=payment_id, refund=refund)

