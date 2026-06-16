"""FastAPI dependencies for admin API authentication."""

from __future__ import annotations

from typing import Annotated

from fastapi import Header, HTTPException, Request

from app.admin.auth import get_admin_api_key, verify_admin_key
from app.utils.metrics import record_admin_request


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _extract_admin_key(
    x_admin_key: str | None,
    x_api_key: str | None,
) -> str | None:
    return x_admin_key or x_api_key


async def admin_required(
    request: Request,
    x_admin_key: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    """
    Require valid ADMIN_API_KEY via X-Admin-Key or X-API-Key header.

    Returns the verified admin key marker (not the raw key).
    """
    if not get_admin_api_key():
        record_admin_request(request.url.path, 503)
        raise HTTPException(status_code=503, detail="ADMIN_API_KEY not configured on server")

    key = _extract_admin_key(x_admin_key, x_api_key)
    ip = _client_ip(request)

    if not verify_admin_key(key, client_ip=ip):
        record_admin_request(request.url.path, 401)
        raise HTTPException(status_code=401, detail="Invalid or unauthorized admin API key")

    request.state.is_admin = True
    request.state.admin_ip = ip
    record_admin_request(request.url.path, 200)
    return "admin"
