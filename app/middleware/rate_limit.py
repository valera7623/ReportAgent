"""Rate limiting middleware for user API endpoints."""

from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.admin.rate_limiter import ADMIN_RATE_LIMIT, check_rate_limit
from app.utils.logger import get_logger
from app.utils.metrics import record_rate_limit_exceeded

logger = get_logger("rate_limit_middleware", "log_api.log")

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


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply Redis sliding-window rate limits after authentication."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path
        if _is_exempt(path):
            return await call_next(request)

        is_admin = path.startswith("/admin/")
        user_id = getattr(request.state, "user_id", None)

        if not is_admin and not user_id and _auth_disabled():
            return await call_next(request)

        if is_admin:
            allowed = check_rate_limit("admin", is_admin=True)
            if not allowed:
                record_rate_limit_exceeded("admin")
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"Admin rate limit exceeded ({ADMIN_RATE_LIMIT}/min)"},
                )
            return await call_next(request)

        if not user_id:
            return await call_next(request)

        if not check_rate_limit(user_id):
            record_rate_limit_exceeded(user_id)
            logger.warning("Rate limit exceeded for user %s on %s", user_id, path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
            )

        return await call_next(request)
