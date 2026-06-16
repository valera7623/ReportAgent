"""Pydantic models for YooKassa payment integration."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class YooKassaPlanType(str, Enum):
    premium_monthly = "premium_monthly"
    premium_yearly = "premium_yearly"
    enterprise = "enterprise"


class YooKassaCreatePaymentRequest(BaseModel):
    plan_type: YooKassaPlanType


class YooKassaCreatePaymentResponse(BaseModel):
    payment_id: str
    confirmation_url: HttpUrl


class YooKassaPaymentStatusResponse(BaseModel):
    payment_id: str
    status: str


class YooKassaSubscriptionResponse(BaseModel):
    plan_type: str
    status: str
    is_active: bool
    monthly_reports_limit: int
    used_reports: int
    remaining_reports: int
    expires_at: str | None = None
    period_start: str | None = None
    period_end: str | None = None


class YooKassaAmount(BaseModel):
    value: str
    currency: str


class YooKassaPaymentObject(BaseModel):
    id: str
    status: str
    amount: YooKassaAmount | None = None
    description: str | None = None
    payment_method: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class YooKassaWebhookNotification(BaseModel):
    # Fixed in docs: type == "notification"
    type: str
    event: str
    object: YooKassaPaymentObject

