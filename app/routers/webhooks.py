"""Webhook CRUD endpoints (authenticated via X-API-Key)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, HttpUrl

from app.webhook.registration import (
    get_webhook,
    get_webhooks_for_user,
    reactivate_webhook,
    register_webhook,
    unregister_webhook,
    update_webhook,
)
from app.utils.logger import get_logger

logger = get_logger("webhooks_router", "log_webhook.log")

router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])


class WebhookRegisterRequest(BaseModel):
    url: HttpUrl
    events: list[str] = Field(default_factory=lambda: ["report.completed"])
    secret: str | None = Field(default=None, max_length=256)


class WebhookUpdateRequest(BaseModel):
    url: HttpUrl | None = None
    events: list[str] | None = None
    is_active: bool | None = None
    secret: str | None = Field(default=None, max_length=256)


class WebhookResponse(BaseModel):
    id: str
    user_id: str
    url: str
    events: list[str]
    created_at: str
    is_active: bool
    last_triggered_at: str | None = None
    failure_count: int = 0


class WebhookRegisterResponse(BaseModel):
    webhook_id: str
    message: str


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return user_id


def _to_response(data: dict[str, Any]) -> WebhookResponse:
    return WebhookResponse(
        id=data["id"],
        user_id=data["user_id"],
        url=data["url"],
        events=data["events"],
        created_at=data["created_at"],
        is_active=data["is_active"],
        last_triggered_at=data.get("last_triggered_at"),
        failure_count=data.get("failure_count", 0),
    )


@router.post("/register", response_model=WebhookRegisterResponse, status_code=201)
async def register_webhook_endpoint(
    request: Request,
    body: WebhookRegisterRequest,
) -> WebhookRegisterResponse:
    """Register a webhook URL for report events."""
    user_id = _require_user_id(request)
    try:
        webhook_id = register_webhook(
            user_id,
            str(body.url),
            secret=body.secret,
            events=body.events,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("Registered webhook %s for user %s", webhook_id, user_id)
    return WebhookRegisterResponse(
        webhook_id=webhook_id,
        message="Webhook registered successfully",
    )


@router.get("", response_model=list[WebhookResponse])
async def list_webhooks(request: Request) -> list[WebhookResponse]:
    """List all webhooks for the authenticated user."""
    user_id = _require_user_id(request)
    return [_to_response(wh) for wh in get_webhooks_for_user(user_id)]


@router.put("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook_endpoint(
    webhook_id: str,
    request: Request,
    body: WebhookUpdateRequest,
) -> WebhookResponse:
    """Update webhook URL, events, secret, or active status."""
    user_id = _require_user_id(request)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    try:
        updated = update_webhook(
            webhook_id,
            user_id,
            url=str(updates["url"]) if "url" in updates else None,
            events=updates.get("events"),
            is_active=updates.get("is_active"),
            secret=updates.get("secret"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if updated is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return _to_response(updated)


@router.post("/{webhook_id}/reactivate", response_model=WebhookResponse)
async def reactivate_webhook_endpoint(webhook_id: str, request: Request) -> WebhookResponse:
    """Re-enable a deactivated webhook and reset failure_count."""
    user_id = _require_user_id(request)
    updated = reactivate_webhook(webhook_id, user_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return _to_response(updated)


@router.delete("/{webhook_id}", status_code=204, response_class=Response)
async def delete_webhook(webhook_id: str, request: Request) -> Response:
    """Unregister a webhook."""
    user_id = _require_user_id(request)
    if not unregister_webhook(webhook_id, user_id):
        raise HTTPException(status_code=404, detail="Webhook not found")
    logger.info("Deleted webhook %s for user %s", webhook_id, user_id)
    return Response(status_code=204)
