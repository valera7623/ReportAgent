"""FastAPI middleware for Prometheus HTTP request metrics."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.utils.metrics import (
    hash_user_id,
    http_request_duration_seconds,
    report_requests_total,
)
from app.utils.logger import get_logger

logger = get_logger("metrics_middleware", "log_api.log")

IGNORED_PATHS = frozenset(
    {
        "/metrics",
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    }
)

IGNORED_PREFIXES = (
    "/docs/",
    "/redoc/",
)


def _should_track(path: str) -> bool:
    if path in IGNORED_PATHS:
        return False
    return not any(path.startswith(prefix) for prefix in IGNORED_PREFIXES)


def _normalize_endpoint(path: str) -> str:
    """Collapse dynamic segments for lower cardinality."""
    if path.startswith("/tasks/"):
        if path.endswith("/pdf"):
            return "/tasks/{task_id}/pdf"
        return "/tasks/{task_id}"
    return path


class MetricsMiddleware(BaseHTTPMiddleware):
    """Count requests, record duration, attach hashed user_id label."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path
        if not _should_track(path):
            return await call_next(request)

        endpoint = _normalize_endpoint(path)
        method = request.method

        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        user_id = getattr(request.state, "user_id", None)
        user_hash = hash_user_id(user_id)
        status = str(response.status_code)
        report_requests_total.labels(
            endpoint=endpoint,
            status=status,
            user_id_hash=user_hash,
        ).inc()
        http_request_duration_seconds.labels(
            endpoint=endpoint,
            method=method,
        ).observe(duration)

        return response
