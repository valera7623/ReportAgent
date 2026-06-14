"""Admin API for webhook delivery statistics."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.webhook.registration import get_webhook_stats
from app.utils.logger import get_logger

logger = get_logger("admin_webhooks", "log_webhook.log")

router = APIRouter(prefix="/admin/webhooks", tags=["admin-webhooks"])


class WebhookStatsResponse(BaseModel):
    total_webhooks: int
    active_webhooks: int
    deactivated_webhooks: int
    high_failure_webhooks: int


def verify_admin_key(x_admin_key: Annotated[str | None, Header()] = None) -> None:
    expected = os.getenv("ADMIN_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY not configured")
    if not x_admin_key or x_admin_key != expected:
        raise HTTPException(status_code=403, detail="Invalid admin API key")


@router.get("/stats", response_model=WebhookStatsResponse, dependencies=[Depends(verify_admin_key)])
async def webhook_stats() -> WebhookStatsResponse:
    """Return webhook registration and health statistics."""
    stats = get_webhook_stats()
    return WebhookStatsResponse(**stats)
