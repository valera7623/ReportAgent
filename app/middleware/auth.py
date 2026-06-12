"""API key authentication middleware."""

from __future__ import annotations

import os
import re

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.db.database import get_user_by_api_key, mask_api_key, update_last_used_at
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
    }
)

EXEMPT_PREFIXES = (
    "/docs/",
    "/redoc/",
)


def _is_exempt(path: str) -> bool:
    if path in EXEMPT_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)


def _auth_disabled() -> bool:
    return os.getenv("DISABLE_AUTH", "").lower() in ("1", "true", "yes")


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
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")

        if not api_key:
            if _auth_disabled():
                request.state.user_id = None
                request.state.api_key = None
                logger.debug("Auth disabled; allowing unauthenticated request to %s", path)
                return await call_next(request)
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or inactive API key"},
            )

        user = get_user_by_api_key(api_key)
        if user is None or not user["is_active"]:
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

        update_last_used_at(user["id"])
        request.state.user_id = user["id"]
        request.state.api_key = api_key

        logger.debug(
            "Authenticated user %s (key %s) for %s %s",
            user["id"],
            mask_api_key(api_key),
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
