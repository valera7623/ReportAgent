"""API key generation endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, EmailStr, Field

from app.db.database import create_user, mask_api_key
from app.utils.logger import get_logger

logger = get_logger("keys_router", "log_api.log")

router = APIRouter(prefix="/api/keys", tags=["API Keys"])


class GenerateKeyRequest(BaseModel):
    email: EmailStr | None = Field(
        default=None,
        description="Optional email stored on the user record for report delivery",
    )


class GenerateKeyResponse(BaseModel):
    api_key: str
    user_id: str


@router.post("/generate", response_model=GenerateKeyResponse, status_code=201)
async def generate_api_key(body: GenerateKeyRequest | None = None) -> GenerateKeyResponse:
    """
    Create a new user and API key.

    No authentication required — intended for first-time onboarding.
    """
    email = body.email if body else None
    user_id, api_key = create_user(email=email)
    logger.info("Generated API key %s for user %s", mask_api_key(api_key), user_id)
    return GenerateKeyResponse(api_key=api_key, user_id=user_id)
