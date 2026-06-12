"""Log authenticated requests to history table."""

from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.db.database import log_history
from app.middleware.auth import extract_task_id_from_path
from app.utils.logger import get_logger

logger = get_logger("request_logging", "log_api.log")


def _build_request_summary(request: Request) -> str:
    """Build summary without consuming request body."""
    query = request.url.query
    base = f"{request.method} {request.url.path}"
    if query:
        return f"{base}?{query}"[:100]
    return base[:100]


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Write history row for each authenticated API request."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        user_id = getattr(request.state, "user_id", None)
        summary = _build_request_summary(request) if user_id else ""

        response = await call_next(request)

        if not user_id:
            return response

        task_id = extract_task_id_from_path(request.url.path)

        if request.url.path == "/generate_report" and response.status_code == 202:
            try:
                body = b""
                async for chunk in response.body_iterator:
                    body += chunk
                payload = json.loads(body.decode())
                task_id = payload.get("task_id") or task_id

                response = Response(
                    content=body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )
            except Exception as exc:
                logger.warning("Could not parse generate_report response for history: %s", exc)

        try:
            log_history(user_id, summary, task_id)
        except Exception as exc:
            logger.error("Failed to log history for user %s: %s", user_id, exc)

        return response
