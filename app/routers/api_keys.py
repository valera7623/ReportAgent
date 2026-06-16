"""API key management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.auth.key_management import (
    generate_api_key,
    list_user_keys,
    rename_api_key,
    revoke_api_key,
    rotate_api_key,
    verify_api_key,
)
from app.db.database import create_user, mask_api_key
from app.models.api_key import (
    ApiKeyCreate,
    ApiKeyGenerateResponse,
    ApiKeyListItem,
    ApiKeyListResponse,
    ApiKeyRenameRequest,
    ApiKeyResponse,
    ApiKeyRevokeResponse,
    ApiKeyRotateRequest,
    ApiKeyRotateResponse,
)
from app.utils.logger import get_logger
from app.utils.metrics import record_api_key_generated

logger = get_logger("api_keys_router", "log_api.log")

router = APIRouter(prefix="/api/keys", tags=["API Keys"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return user_id


def _current_key_id(request: Request) -> str | None:
    return getattr(request.state, "key_id", None)


@router.get("", response_model=ApiKeyListResponse)
async def list_keys(request: Request) -> ApiKeyListResponse:
    """List all API keys for the authenticated user (masked — prefix only)."""
    user_id = _require_user_id(request)
    current_id = _current_key_id(request)
    keys = list_user_keys(user_id)
    items = [
        ApiKeyListItem(
            **key.model_dump(),
            is_current=(key.id == current_id) if current_id else False,
        )
        for key in keys
    ]
    return ApiKeyListResponse(keys=items)


@router.post("/generate", response_model=ApiKeyGenerateResponse, status_code=201)
async def generate_key_endpoint(
    request: Request,
    body: ApiKeyCreate | None = None,
) -> ApiKeyGenerateResponse:
    """
    Generate a new API key.

    - **No authentication**: creates a new user account (onboarding) + first key.
    - **With X-API-Key**: adds another key to the existing user.

    The full key is returned **only once** — save it securely.
    """
    payload = body or ApiKeyCreate()
    user_id = getattr(request.state, "user_id", None)

    if not user_id:
        header_key = request.headers.get("X-API-Key")
        if header_key:
            auth = verify_api_key(header_key, client_ip=_client_ip(request))
            if auth:
                user_id = auth["user_id"]

    if not user_id:
        user_id, full_key, key_id = create_user(
            email=str(payload.email) if payload.email else None,
            name=payload.name,
        )
        record_api_key_generated()
        logger.info(
            "Onboarding: created user %s with key %s",
            user_id,
            mask_api_key(full_key),
        )
        return ApiKeyGenerateResponse(
            id=key_id,
            key=full_key,
            key_prefix=full_key[:8],
            name=payload.name,
            user_id=user_id,
        )

    full_key, key_id = generate_api_key(
        user_id,
        name=payload.name,
        expires_at=payload.expires_at,
    )

    return ApiKeyGenerateResponse(
        id=key_id,
        key=full_key,
        key_prefix=full_key[:8],
        name=payload.name,
        user_id=None,
    )


@router.delete("/{key_id}", response_model=ApiKeyRevokeResponse)
async def revoke_key_endpoint(key_id: str, request: Request) -> ApiKeyRevokeResponse:
    """Revoke (deactivate) an API key. Cannot revoke the last active key."""
    user_id = _require_user_id(request)
    try:
        prefix = revoke_api_key(key_id, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if prefix is None:
        raise HTTPException(status_code=404, detail="API key not found")

    return ApiKeyRevokeResponse(key_prefix=prefix)


@router.post("/{key_id}/rotate", response_model=ApiKeyRotateResponse)
async def rotate_key_endpoint(
    key_id: str,
    request: Request,
    body: ApiKeyRotateRequest | None = None,
) -> ApiKeyRotateResponse:
    """Rotate an API key: revoke the old one and return a new full key (shown once)."""
    user_id = _require_user_id(request)
    new_name = body.new_name if body else None
    try:
        new_key, new_key_id, old_prefix = rotate_api_key(key_id, user_id, new_name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ApiKeyRotateResponse(
        old_key_prefix=old_prefix,
        new_key=new_key,
        new_key_id=new_key_id,
    )


@router.put("/{key_id}/rename", response_model=ApiKeyResponse)
async def rename_key_endpoint(
    key_id: str,
    request: Request,
    body: ApiKeyRenameRequest,
) -> ApiKeyResponse:
    """Rename an API key."""
    user_id = _require_user_id(request)
    updated = rename_api_key(key_id, user_id, body.name)
    if updated is None:
        raise HTTPException(status_code=404, detail="API key not found")
    return updated
