"""Dashboard statistics for frontend."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.db.database import get_dashboard_stats
from app.utils.logger import get_logger

logger = get_logger("dashboard_router", "log_api.log")

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


class DashboardStatsResponse(BaseModel):
    total_reports_last_30_days: int
    success_rate: float
    most_used_output_format: str
    average_generation_time_seconds: float
    active_webhooks_count: int


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return user_id


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_stats(request: Request) -> DashboardStatsResponse:
    """Return aggregated report metrics for the authenticated user (last 30 days)."""
    user_id = _require_user_id(request)
    stats = get_dashboard_stats(user_id)
    logger.debug("Dashboard stats for user %s: %s", user_id, stats)
    return DashboardStatsResponse(**stats)
