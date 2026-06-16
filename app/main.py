"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from celery.result import AsyncResult
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.agents.parser import save_upload, validate_request
from app.celery_app import celery_app
from app.config.output_formats import EXTERNAL_FORMATS, resolve_output_format
from app.db.database import get_usage_count, log_history, resolve_email_for_user
from app.db.init_db import run_migrations
from app.middleware.auth import APIKeyAuthMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware
from app.self_healing.init_kb import init_knowledge_base
from app.utils.metrics import get_metrics_payload, start_background_gauge_updaters
from app.utils.metrics_middleware import MetricsMiddleware
from app.models.schemas import (
    AgentError,
    GenerateReportResponse,
    TaskState,
    TaskStatusResponse,
)
from app.routers import (
    admin,
    admin_self_healing,
    admin_webhooks,
    api_keys,
    dashboard,
    preferences,
    reports_api,
    voice,
    webhooks,
)
from app.tasks import generate_report
from app.voice.config import voice_available
from app.voice.redis_store import get_voice_status, load_partial_state
from app.utils.logger import get_logger
from app.utils.paths import resolve_formatted_path, resolve_pdf_path

logger = get_logger("main", "log_api.log")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        run_migrations()
    except Exception as exc:
        logger.exception("Database migration failed on startup: %s", exc)
        raise
    try:
        init_knowledge_base()
    except Exception as exc:
        logger.warning("Self-healing knowledge base init failed (non-fatal): %s", exc)
    start_background_gauge_updaters()
    yield


app = FastAPI(
    title="ReportAgent",
    description=(
        "Upload CSV/Excel or provide a public Google Sheets URL to generate reports "
        "in PDF, Excel, PowerPoint, Notion, or Google Slides. "
        "Receive by email or download via API. "
        "Authenticate with X-API-Key header (generate via POST /api/keys/generate)."
    ),
    version="1.8.0",
    lifespan=lifespan,
)

app.add_middleware(MetricsMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(APIKeyAuthMiddleware)

app.include_router(admin.router)
app.include_router(api_keys.router)
app.include_router(preferences.router)
app.include_router(voice.router)
app.include_router(admin_self_healing.router)
app.include_router(admin_webhooks.router)
app.include_router(webhooks.router)
app.include_router(dashboard.router)
app.include_router(reports_api.router)


def _download_url_for_format(task_id: str, output_format: str) -> str:
    if output_format == "pdf":
        return f"/tasks/{task_id}/pdf"
    return f"/tasks/{task_id}/export"


def _build_queue_message(email: str | None, task_id: str, output_format: str) -> str:
    download_hint = f"Download at GET {_download_url_for_format(task_id, output_format)} when ready."
    if output_format in EXTERNAL_FORMATS:
        download_hint = f"External link at GET /tasks/{task_id}/export when ready."
    if email and output_format == "pdf":
        return f"Report generation started. PDF will be emailed to {email}. {download_hint}"
    return f"Report generation started ({output_format}). {download_hint}"


def _validate_format_credentials(output_format: str) -> None:
    """Return 400 if external format requested without credentials."""
    import os

    if output_format == "notion":
        if not os.getenv("NOTION_INTEGRATION_TOKEN", "").strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Notion export requires NOTION_INTEGRATION_TOKEN. "
                    "Configure .env or choose another output_format."
                ),
            )
        if not os.getenv("NOTION_DATABASE_ID", "").strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Notion export requires NOTION_DATABASE_ID. "
                    "Configure .env or choose another output_format."
                ),
            )
    if output_format == "google_slides":
        sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "./secrets/google-sa.json")
        if not Path(sa_path).is_file():
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Google Slides export requires service account JSON at {sa_path}. "
                    "Mount secrets/google-sa.json or choose another output_format."
                ),
            )
        if not os.getenv("GOOGLE_SLIDES_TEMPLATE_ID", "").strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Google Slides export requires GOOGLE_SLIDES_TEMPLATE_ID. "
                    "Configure .env or choose another output_format."
                ),
            )


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "ReportAgent",
        "docs": "/docs",
        "health": "/health",
        "sample_csv": "/samples/sample_sales.csv",
        "api_keys": "/api/keys/generate",
        "voice": "/voice/generate_report" if voice_available() else "disabled",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics exposition (no authentication)."""
    return Response(content=get_metrics_payload(), media_type="text/plain; version=0.0.4; charset=utf-8")


@app.get("/samples/sample_sales.csv")
async def get_sample_csv() -> FileResponse:
    """Download test CSV for Swagger/manual testing."""
    sample_path = Path(__file__).resolve().parent / "samples" / "sample_sales.csv"
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Sample CSV not found.")
    return FileResponse(
        sample_path,
        media_type="text/csv",
        filename="sample_sales.csv",
    )


@app.post("/generate_report", response_model=GenerateReportResponse, status_code=202)
async def generate_report_endpoint(
    request: Request,
    sheets_url: Annotated[str | None, Form(description="Public Google Sheets URL")] = None,
    email: Annotated[str | None, Form(description="Optional recipient email")] = None,
    output_format: Annotated[
        str | None,
        Form(description="Output format: pdf, excel, pptx, notion, google_slides"),
    ] = None,
    file: UploadFile | None = File(default=None, description="CSV or Excel file"),
) -> GenerateReportResponse:
    """
    Queue report generation.

    Provide **either** a file upload **or** a public Google Sheets URL.
    Email is optional — uses saved default from preferences when omitted.
    output_format is optional — uses preferences.default_output_format or pdf.
    Requires **X-API-Key** header (unless DISABLE_AUTH=true).
    """
    has_file = file is not None and file.filename not in (None, "")
    sheets_url_clean = sheets_url.strip() if sheets_url else None
    email_clean = email.strip() if email else None
    output_format_clean = output_format.strip().lower() if output_format else None

    user_id = getattr(request.state, "user_id", None)
    api_key = getattr(request.state, "api_key", None)

    from app.agents.context_loader import get_user_preferences

    prefs = get_user_preferences(api_key)
    try:
        resolved_format = resolve_output_format(output_format_clean, prefs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _validate_format_credentials(resolved_format)

    if user_id:
        email_clean = resolve_email_for_user(user_id, email_clean)

    try:
        validate_request(email=email_clean, sheets_url=sheets_url_clean, has_file=has_file)
    except AgentError as exc:
        logger.warning("Validation failed: %s", exc.message)
        raise HTTPException(status_code=400, detail=exc.message) from exc

    file_path: str | None = None

    if has_file and file is not None:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        try:
            saved = save_upload(content, file.filename or "upload.csv")
            file_path = str(saved)
        except AgentError as exc:
            raise HTTPException(status_code=400, detail=exc.message) from exc

    task = generate_report.delay(
        email=email_clean,
        sheets_url=sheets_url_clean,
        file_path=file_path,
        api_key=api_key,
        output_format=resolved_format,
    )

    usage_count = 0
    if user_id:
        usage_count = get_usage_count(user_id) + 1
        log_history(
            user_id,
            f"POST /generate_report format={resolved_format}",
            task.id,
            output_format=resolved_format,
        )

    download_url = _download_url_for_format(task.id, resolved_format)
    logger.info(
        "Queued task %s (email=%s, user=%s, format=%s)",
        task.id,
        email_clean or "none",
        user_id or "anon",
        resolved_format,
    )
    return GenerateReportResponse(
        task_id=task.id,
        message=_build_queue_message(email_clean, task.id, resolved_format),
        download_url=download_url,
        output_format=resolved_format,
        user_id=user_id,
        usage_count=usage_count,
    )


def _get_task_result_or_raise(task_id: str) -> dict:
    result = AsyncResult(task_id, app=celery_app)

    if result.state in ("PENDING", "STARTED"):
        raise HTTPException(
            status_code=202,
            detail="Report is still being generated. Try again shortly.",
        )

    if result.state == "FAILURE":
        error_msg = str(result.result)
        raise HTTPException(status_code=400, detail=f"Report generation failed: {error_msg}")

    if result.state != "SUCCESS":
        raise HTTPException(status_code=404, detail=f"Unknown task state: {result.state}")

    if not isinstance(result.result, dict):
        raise HTTPException(status_code=500, detail="Invalid task result format.")

    return result.result


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """Check Celery task status and result."""
    voice_status = get_voice_status(task_id)
    if voice_status == "needs_clarification":
        partial = load_partial_state(task_id) or {}
        return TaskStatusResponse(
            task_id=task_id,
            status=TaskState.NEEDS_CLARIFICATION,
            result={
                "clarification_question": partial.get("clarification_question"),
                "partial_intent": partial.get("partial_intent"),
                "transcript": partial.get("transcript"),
            },
        )

    result = AsyncResult(task_id, app=celery_app)

    state = result.state
    if state == "PENDING":
        return TaskStatusResponse(task_id=task_id, status=TaskState.PENDING)
    if state == "STARTED":
        return TaskStatusResponse(task_id=task_id, status=TaskState.STARTED)
    if state == "SUCCESS":
        payload = result.result if isinstance(result.result, dict) else {"result": result.result}
        if isinstance(payload, dict):
            fmt = payload.get("output_format", "pdf")
            payload = {
                **payload,
                "download_url": payload.get("download_url") or _download_url_for_format(task_id, fmt),
            }
        return TaskStatusResponse(
            task_id=task_id,
            status=TaskState.SUCCESS,
            result=payload,
        )
    if state == "FAILURE":
        error_msg = str(result.result)
        meta = result.info if isinstance(result.info, dict) else {}
        if isinstance(meta, dict) and "error" in meta:
            error_msg = meta["error"]
        return TaskStatusResponse(
            task_id=task_id,
            status=TaskState.FAILURE,
            error=error_msg,
        )

    return TaskStatusResponse(task_id=task_id, status=TaskState(state))


@app.get("/tasks/{task_id}/pdf")
async def download_report_pdf(task_id: str) -> FileResponse:
    """Download generated PDF. No email required. Backward-compatible endpoint."""
    payload = _get_task_result_or_raise(task_id)

    pdf_path_value: str | None = payload.get("pdf_path") or payload.get("file_path")
    pdf_path = resolve_pdf_path(task_id, pdf_path_value)
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="PDF file not found for this task.")

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"report_{task_id}.pdf",
    )


@app.get("/tasks/{task_id}/export")
async def export_report(task_id: str) -> Response:
    """
    Download formatted report or redirect to external URL (Notion / Google Slides).
    """
    payload = _get_task_result_or_raise(task_id)
    output_format = payload.get("output_format", "pdf")
    content_type = payload.get("content_type", "application/octet-stream")

    external_url = payload.get("external_url")
    if external_url:
        return RedirectResponse(url=external_url, status_code=302)

    if output_format == "pdf":
        pdf_path = resolve_pdf_path(task_id, payload.get("pdf_path") or payload.get("file_path"))
        if not pdf_path.is_file():
            raise HTTPException(status_code=404, detail="PDF file not found for this task.")
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"report_{task_id}.pdf",
        )

    file_path = resolve_formatted_path(
        task_id,
        output_format,
        payload.get("file_path"),
    )
    if file_path is None or not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Export file not found for format '{output_format}'.",
        )

    ext = file_path.suffix.lstrip(".") or output_format
    return FileResponse(
        file_path,
        media_type=content_type,
        filename=f"report_{task_id}.{ext}",
    )


@app.exception_handler(AgentError)
async def agent_error_handler(_request, exc: AgentError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message, "agent": exc.agent},
    )


_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if _FRONTEND_DIR.is_dir() and (_FRONTEND_DIR / "index.html").is_file():
    app.mount(
        "/app",
        StaticFiles(directory=str(_FRONTEND_DIR), html=True),
        name="frontend",
    )
