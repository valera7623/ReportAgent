"""OAuth login scaffold (Google / Microsoft) — enabled when client IDs are configured."""

from __future__ import annotations

import os
import secrets
import urllib.parse

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/auth/oauth", tags=["OAuth"])


def _site_url() -> str:
    return (
        os.getenv("SITE_URL", "").strip()
        or os.getenv("FRONTEND_URL", "").strip().removesuffix("/app")
        or "http://localhost:8000"
    ).rstrip("/")


def _google_enabled() -> bool:
    return bool(os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip() and os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip())


def _microsoft_enabled() -> bool:
    return bool(
        os.getenv("MICROSOFT_OAUTH_CLIENT_ID", "").strip()
        and os.getenv("MICROSOFT_OAUTH_CLIENT_SECRET", "").strip()
    )


@router.get("/providers")
async def oauth_providers() -> dict[str, bool]:
    return {"google": _google_enabled(), "microsoft": _microsoft_enabled()}


@router.get("/google")
async def oauth_google_start() -> RedirectResponse:
    if not _google_enabled():
        raise HTTPException(status_code=501, detail="Google OAuth is not configured")
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    redirect_uri = f"{_site_url()}/auth/oauth/google/callback"
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return RedirectResponse(url)


@router.get("/google/callback")
async def oauth_google_callback(
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    if error or not code:
        return RedirectResponse(f"{_site_url()}/app#/login?oauth_error=google")
    # Full token exchange + user provisioning is roadmap — redirect to login for now.
    return RedirectResponse(f"{_site_url()}/app#/login?oauth=google_pending")


@router.get("/microsoft")
async def oauth_microsoft_start() -> RedirectResponse:
    if not _microsoft_enabled():
        raise HTTPException(status_code=501, detail="Microsoft OAuth is not configured")
    client_id = os.getenv("MICROSOFT_OAUTH_CLIENT_ID", "").strip()
    redirect_uri = f"{_site_url()}/auth/oauth/microsoft/callback"
    tenant = os.getenv("MICROSOFT_OAUTH_TENANT", "common").strip() or "common"
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile User.Read",
        "state": state,
    }
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?" + urllib.parse.urlencode(params)
    return RedirectResponse(url)


@router.get("/microsoft/callback")
async def oauth_microsoft_callback(
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    if error or not code:
        return RedirectResponse(f"{_site_url()}/app#/login?oauth_error=microsoft")
    return RedirectResponse(f"{_site_url()}/app#/login?oauth=microsoft_pending")
