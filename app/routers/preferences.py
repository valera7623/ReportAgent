"""User preferences management endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from app.db.database import (
    get_user_preferences,
    reset_user_preferences,
    update_user_preferences,
)
from app.utils.logger import get_logger

logger = get_logger("preferences_router", "log_api.log")

router = APIRouter(prefix="/api/preferences", tags=["Preferences"])


class PreferencesResponse(BaseModel):
    preferred_chart_type: str
    theme: str
    default_email: str | None = None
    company_logo_url: str | None = None
    timezone: str
    extra: dict[str, Any] = Field(default_factory=dict)


class PreferencesUpdateRequest(BaseModel):
    preferred_chart_type: str | None = Field(default=None, pattern="^(bar|line|pie)$")
    theme: str | None = Field(default=None, pattern="^(light|dark)$")
    default_email: EmailStr | None = None
    company_logo_url: str | None = None
    timezone: str | None = None
    extra: dict[str, Any] | None = None


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return user_id


@router.get("", response_model=PreferencesResponse)
async def get_preferences(request: Request) -> PreferencesResponse:
    """Return current user preferences."""
    user_id = _require_user_id(request)
    prefs = get_user_preferences(user_id)
    return PreferencesResponse(**prefs)


@router.put("", response_model=PreferencesResponse)
async def update_preferences(
    request: Request,
    body: PreferencesUpdateRequest,
) -> PreferencesResponse:
    """Update user preferences (partial update supported)."""
    user_id = _require_user_id(request)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No preference fields provided")

    try:
        prefs = update_user_preferences(user_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("Updated preferences for user %s", user_id)
    return PreferencesResponse(**prefs)


@router.delete("", response_model=PreferencesResponse)
async def reset_preferences(request: Request) -> PreferencesResponse:
    """Reset preferences to defaults."""
    user_id = _require_user_id(request)
    prefs = reset_user_preferences(user_id)
    logger.info("Reset preferences for user %s", user_id)
    return PreferencesResponse(**prefs)
