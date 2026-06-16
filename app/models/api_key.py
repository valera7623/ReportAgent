"""Pydantic models for API key management."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(default="Default", max_length=100)
    expires_at: datetime | None = None
    email: EmailStr | None = Field(
        default=None,
        description="Optional email for new user onboarding (no auth required)",
    )


class ApiKeyResponse(BaseModel):
    id: str
    key_prefix: str
    name: str
    created_at: datetime | str
    last_used_at: datetime | str | None = None
    expires_at: datetime | str | None = None
    is_active: bool = True


class ApiKeyListItem(ApiKeyResponse):
    is_current: bool = False


class ApiKeyFullResponse(ApiKeyResponse):
    full_key: str = Field(description="Full key — shown only once at generation time")


class ApiKeyGenerateResponse(BaseModel):
    id: str
    key: str = Field(description="Full key — shown only once; save it securely")
    key_prefix: str
    name: str
    user_id: str | None = Field(
        default=None,
        description="Present when a new user account is created during onboarding",
    )


class ApiKeyRotateRequest(BaseModel):
    new_name: str | None = Field(default=None, max_length=100)


class ApiKeyRotateResponse(BaseModel):
    old_key_prefix: str
    new_key: str
    new_key_id: str


class ApiKeyRenameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class ApiKeyRevokeResponse(BaseModel):
    status: str = "revoked"
    key_prefix: str


class ApiKeyListResponse(BaseModel):
    keys: list[ApiKeyListItem]
