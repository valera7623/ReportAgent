"""Middleware: block report generation when monthly limit is exceeded."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.payments.usage_tracker import check_report_limit

REPORT_LIMIT_PATHS = frozenset(
    {
        "/generate_report",
        "/voice/generate_report",
        "/voice/clarify",
    }
)


class UsageLimitMiddleware(BaseHTTPMiddleware):
    """Return 402 before handler when user has no remaining report slots."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if request.method == "POST" and path in REPORT_LIMIT_PATHS:
            user_id = getattr(request.state, "user_id", None)
            if user_id and not check_report_limit(user_id):
                return JSONResponse(
                    status_code=402,
                    content={
                        "detail": {
                            "message": "Лимит отчётов исчерпан. Оформите подписку.",
                            "upgrade_url": "/app#/pricing",
                            "code": "report_limit_exceeded",
                        }
                    },
                    headers={"X-Upgrade-Url": "/app#/pricing"},
                )
        return await call_next(request)
