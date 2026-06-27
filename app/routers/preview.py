"""Report preview API endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field

from app.agents.context_loader import get_user_preferences
from app.agents.parser import validate_request
from app.config.output_formats import resolve_output_format, validate_format_credentials
from app.db.database import log_history, resolve_email_for_user
from app.models.schemas import AgentError, GenerateReportResponse
from app.payments.usage_tracker import consume_report_slot
from app.preview.cache import delete_preview, get_chart_png, get_job_result, get_preview, preview_storage_dir, store_job_result, store_preview
from app.preview.generator import PreviewGenerator, file_size_mb
from app.tasks import generate_report, preview_generation_task
from app.utils.logger import get_logger
from app.utils.metrics import record_preview_confirmed, record_preview_generated

logger = get_logger("preview_router", "log_api.log")

router = APIRouter(tags=["Preview"])

ASYNC_THRESHOLD_MB = int(__import__("os").getenv("PREVIEW_ASYNC_THRESHOLD_MB", "10"))


class PreviewConfirmRequest(BaseModel):
    preview_id: str
    email: EmailStr | None = None
    output_format: str | None = None


class RegenerateChartRequest(BaseModel):
    preview_id: str
    chart_index: int = Field(ge=0)
    chart_type: str = Field(pattern="^(bar|line|pie)$")


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return user_id


def _get_preview_for_user(preview_id: str, user_id: str) -> dict[str, Any]:
    record = get_preview(preview_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Preview not found or expired")
    if record.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Preview access denied")
    return record


def _log_preview_action(user_id: str, preview_id: str, action: str) -> None:
    try:
        from app.db.database import get_connection

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO preview_log (user_id, preview_id, action)
                VALUES (?, ?, ?)
                """,
                (user_id, preview_id, action),
            )
    except Exception as exc:
        logger.debug("preview_log insert skipped: %s", exc)


@router.post("/api/reports/preview")
async def create_preview(
    request: Request,
    sheets_url: Annotated[str | None, Form()] = None,
    suggestions_json: Annotated[str | None, Form()] = None,
    file: UploadFile | None = File(default=None),
):
    """
    Generate a report preview (no email, no history).

    Files over 10MB are processed asynchronously — poll GET /api/reports/preview/status/{job_id}.
    """
    user_id = _require_user_id(request)
    api_key = getattr(request.state, "api_key", None)
    has_file = file is not None and file.filename not in (None, "")
    sheets_url_clean = sheets_url.strip() if sheets_url else None

    try:
        validate_request(email=None, sheets_url=sheets_url_clean, has_file=has_file)
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    ai_suggestions: dict[str, Any] | None = None
    if suggestions_json:
        try:
            ai_suggestions = json.loads(suggestions_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid suggestions_json") from exc

    file_path: str | None = None
    if has_file and file is not None:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        preview_id = str(uuid.uuid4())
        dest_dir = preview_storage_dir(preview_id)
        suffix = "." + (file.filename or "upload.csv").rsplit(".", 1)[-1]
        if not suffix.startswith("."):
            suffix = ".csv"
        dest = dest_dir / f"upload{suffix.lower()}"
        dest.write_bytes(content)
        file_path = str(dest)

        if file_size_mb(file_path) > ASYNC_THRESHOLD_MB:
            job = preview_generation_task.delay(
                preview_id=preview_id,
                user_id=user_id,
                file_path=file_path,
                sheets_url=None,
                api_key=api_key,
                ai_suggestions=ai_suggestions,
            )
            store_job_result(
                job.id,
                {"status": "processing", "preview_id": preview_id, "user_id": user_id},
            )
            return {
                "status": "processing",
                "job_id": job.id,
                "preview_id": preview_id,
                "message": "Large file — preview is being generated asynchronously",
            }
    elif sheets_url_clean:
        preview_id = str(uuid.uuid4())
    else:
        raise HTTPException(status_code=400, detail="Provide file or sheets_url")

    prefs = get_user_preferences(api_key)
    started = datetime.now(timezone.utc)

    try:
        result = PreviewGenerator().generate_preview(
            user_id=user_id,
            file_path=file_path,
            sheets_url=sheets_url_clean,
            preferences=prefs,
            preview_id=preview_id,
            ai_suggestions=ai_suggestions,
        )
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    cache_payload = result.pop("_cache_payload")
    cache_payload["status"] = "ready"
    store_preview(preview_id, cache_payload, user_id)
    _log_preview_action(user_id, preview_id, "created")
    record_preview_generated((datetime.now(timezone.utc) - started).total_seconds())

    return {
        "preview_id": result["preview_id"],
        "data": result["data"],
        "expires_at": result["expires_at"],
    }


@router.get("/api/reports/preview/{preview_id}")
async def get_preview_by_id(preview_id: str, request: Request):
    """Fetch ready preview by ID (owner only)."""
    user_id = _require_user_id(request)
    record = _get_preview_for_user(preview_id, user_id)
    return {
        "preview_id": preview_id,
        "status": record.get("status", "ready"),
        "data": record.get("data"),
        "expires_at": record.get("expires_at"),
    }


@router.get("/api/reports/preview/status/{job_id}")
async def preview_job_status(job_id: str, request: Request):
    """Poll async preview generation status."""
    user_id = _require_user_id(request)
    job = get_job_result(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Preview job not found or expired")
    if job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if job.get("status") == "processing":
        return job

    if job.get("status") == "failed":
        return job

    preview_id = job.get("preview_id")
    if preview_id:
        record = get_preview(preview_id)
        if record:
            return {
                "status": "ready",
                "preview_id": preview_id,
                "data": record.get("data"),
                "expires_at": record.get("expires_at"),
            }
    return job


@router.get("/api/preview/chart/{preview_id}/{chart_index}")
async def get_preview_chart(preview_id: str, chart_index: int, request: Request):
    """Serve temporary preview chart PNG."""
    user_id = _require_user_id(request)
    _get_preview_for_user(preview_id, user_id)

    png = get_chart_png(preview_id, chart_index)
    if not png:
        raise HTTPException(status_code=404, detail="Chart not found or expired")

    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/api/reports/preview/confirm", response_model=GenerateReportResponse, status_code=202)
async def confirm_preview(request: Request, body: PreviewConfirmRequest):
    """Confirm preview and queue full report generation."""
    user_id = _require_user_id(request)
    api_key = getattr(request.state, "api_key", None)
    record = _get_preview_for_user(body.preview_id, user_id)

    prefs = get_user_preferences(api_key)
    try:
        resolved_format = resolve_output_format(body.output_format, prefs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    validate_format_credentials(resolved_format)

    email_clean = resolve_email_for_user(user_id, str(body.email) if body.email else None)

    file_path = record.get("file_path")
    sheets_url = record.get("sheets_url")
    if not file_path and not sheets_url:
        raise HTTPException(status_code=400, detail="Preview data source missing")

    usage_count = 0
    slot = consume_report_slot(user_id=user_id, desired_output_format=resolved_format)
    usage_count = slot.used_reports

    task = generate_report.delay(
        email=email_clean,
        sheets_url=sheets_url,
        file_path=file_path,
        api_key=api_key,
        output_format=resolved_format,
        preview_id=body.preview_id,
        ai_suggestions=record.get("ai_suggestions"),
    )

    log_history(
        user_id,
        f"POST /api/reports/preview/confirm format={resolved_format}",
        task.id,
        output_format=resolved_format,
    )
    _log_preview_action(user_id, body.preview_id, "confirmed")
    record_preview_confirmed()
    # Keep uploaded file on disk until Celery reads it (async queue).
    delete_preview(body.preview_id, remove_files=False)

    download_url = f"/tasks/{task.id}/pdf" if resolved_format == "pdf" else f"/tasks/{task.id}/export"
    return GenerateReportResponse(
        task_id=task.id,
        message=f"Report generation started ({resolved_format}).",
        download_url=download_url,
        output_format=resolved_format,
        user_id=user_id,
        usage_count=usage_count,
    )


@router.post("/api/reports/preview/regenerate-chart")
async def regenerate_chart(request: Request, body: RegenerateChartRequest):
    """Regenerate a single preview chart with a different type."""
    user_id = _require_user_id(request)
    record = _get_preview_for_user(body.preview_id, user_id)

    try:
        updated = PreviewGenerator().regenerate_chart(
            preview_id=body.preview_id,
            chart_index=body.chart_index,
            chart_type=body.chart_type,
            preview_record=record,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    store_preview(body.preview_id, record, user_id)
    return updated
