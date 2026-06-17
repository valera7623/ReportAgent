"""API key authentication middleware."""

from __future__ import annotations

import os
import re

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.auth.key_management import verify_api_key
from app.db.database import mask_api_key
from app.utils.logger import get_logger

logger = get_logger("auth_middleware", "log_api.log")

EXEMPT_PATHS = frozenset(
    {
        "/",
        "/health",
        "/metrics",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/keys/generate",
        "/payment/success",
        "/payment/cancel",
        "/success",
        "/cancel",
        "/webhooks/yookassa",
        "/webhooks/stripe",
        "/api/payments/prices",
        "/api/payments/config",
    }
)

EXEMPT_PREFIXES = (
    "/docs/",
    "/redoc/",
    "/admin/",
    "/app/",
)


def _is_exempt(path: str) -> bool:
    if path in EXEMPT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)


def _auth_disabled() -> bool:
    return os.getenv("DISABLE_AUTH", "").lower() in ("1", "true", "yes")


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validate X-API-Key header and attach user context to request.state."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path

        if _is_exempt(path):
            request.state.user_id = None
            request.state.api_key = None
            request.state.key_id = None
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")

        if not api_key:
            if _auth_disabled():
                request.state.user_id = None
                request.state.api_key = None
                request.state.key_id = None
                logger.debug("Auth disabled; allowing unauthenticated request to %s", path)
                return await call_next(request)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or inactive API key"},
            )

        auth = verify_api_key(api_key, client_ip=_client_ip(request))
        if auth is None:
            logger.warning(
                "Rejected API key %s for %s %s",
                mask_api_key(api_key),
                request.method,
                path,
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or inactive API key"},
            )

        request.state.user_id = auth["user_id"]
        request.state.api_key = api_key
        request.state.key_id = auth.get("key_id")

        logger.debug(
            "Authenticated user %s (key %s, source=%s) for %s %s",
            auth["user_id"],
            mask_api_key(api_key),
            auth.get("source", "unknown"),
            request.method,
            path,
        )

        return await call_next(request)


TASK_ID_PATTERN = re.compile(r"^/tasks/([^/]+)")


def extract_task_id_from_path(path: str) -> str | None:
    match = TASK_ID_PATTERN.match(path)
    if match:
        return match.group(1)
    return None
