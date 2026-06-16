"""Admin webhook statistics."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.admin.dependency import admin_required
from app.webhook.registration import get_webhook_stats
from app.utils.logger import get_logger

logger = get_logger("admin_webhooks", "log_webhook.log")

router = APIRouter(prefix="/admin/webhooks", tags=["admin-webhooks"])


class WebhookStatsResponse(BaseModel):
    total_webhooks: int
    active_webhooks: int
    deactivated_webhooks: int
    high_failure_webhooks: int


@router.get("/stats", response_model=WebhookStatsResponse, dependencies=[Depends(admin_required)])
async def webhook_stats() -> WebhookStatsResponse:
    """Return webhook registration and health statistics."""
    stats = get_webhook_stats()
    return WebhookStatsResponse(**stats)
