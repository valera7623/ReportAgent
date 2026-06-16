"""Report history list and delete for frontend."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from app.db.database import delete_user_report, list_user_reports
from app.utils.logger import get_logger
from app.utils.report_storage import delete_task_storage

logger = get_logger("reports_api_router", "log_api.log")

router = APIRouter(prefix="/api/reports", tags=["Reports"])


class ReportItem(BaseModel):
    task_id: str
    created_at: str
    status: str
    output_format: str
    download_url: str
    request_summary: str


class ReportsListResponse(BaseModel):
    reports: list[ReportItem]
    total: int
    page: int
    limit: int


class DeleteReportResponse(BaseModel):
    status: str = "deleted"


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return user_id


@router.get("", response_model=ReportsListResponse)
async def list_reports(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> ReportsListResponse:
    """Paginated report history for the authenticated user."""
    user_id = _require_user_id(request)
    rows, total = list_user_reports(user_id, page=page, limit=limit)
    return ReportsListResponse(
        reports=[ReportItem(**row) for row in rows],
        total=total,
        page=page,
        limit=limit,
    )


@router.delete("/{task_id}", response_model=DeleteReportResponse)
async def delete_report(task_id: str, request: Request) -> DeleteReportResponse:
    """Delete report files and history entry (own tasks only)."""
    user_id = _require_user_id(request)
    if not delete_user_report(user_id, task_id):
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        delete_task_storage(task_id)
    except Exception as exc:
        logger.warning("Storage cleanup failed for task %s: %s", task_id, exc)

    logger.info("Deleted report %s for user %s", task_id, user_id)
    return DeleteReportResponse()
