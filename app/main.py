"""FastAPI application entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from celery.result import AsyncResult
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.agents.parser import save_upload, validate_request
from app.celery_app import celery_app
from app.models.schemas import (
    AgentError,
    GenerateReportResponse,
    TaskState,
    TaskStatusResponse,
)
from app.tasks import generate_report
from app.utils.logger import get_logger
from app.utils.paths import resolve_pdf_path

logger = get_logger("main", "log_api.log")

app = FastAPI(
    title="ReportAgent",
    description=(
        "Upload CSV/Excel or provide a public Google Sheets URL to generate a PDF report. "
        "Receive it by email or download via API."
    ),
    version="1.1.0",
)


def _build_queue_message(email: str | None, task_id: str) -> str:
    download_hint = f"Download at GET /tasks/{task_id}/pdf when ready."
    if email:
        return f"Report generation started. PDF will be emailed to {email}. {download_hint}"
    return f"Report generation started. {download_hint}"


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "ReportAgent",
        "docs": "/docs",
        "health": "/health",
        "sample_csv": "/samples/sample_sales.csv",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
    sheets_url: Annotated[str | None, Form(description="Public Google Sheets URL")] = None,
    email: Annotated[str | None, Form(description="Optional recipient email")] = None,
    file: UploadFile | None = File(default=None, description="CSV or Excel file"),
) -> GenerateReportResponse:
    """
    Queue report generation.

    Provide **either** a file upload **or** a public Google Sheets URL.
    Email is optional — without it, download the PDF via `GET /tasks/{task_id}/pdf`.
    """
    has_file = file is not None and file.filename not in (None, "")
    sheets_url_clean = sheets_url.strip() if sheets_url else None
    email_clean = email.strip() if email else None

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
    )

    logger.info("Queued task %s (email=%s)", task.id, email_clean or "none")
    return GenerateReportResponse(
        task_id=task.id,
        message=_build_queue_message(email_clean, task.id),
        download_url=f"/tasks/{task.id}/pdf",
    )


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """Check Celery task status and result."""
    result = AsyncResult(task_id, app=celery_app)

    state = result.state
    if state == "PENDING":
        return TaskStatusResponse(task_id=task_id, status=TaskState.PENDING)
    if state == "STARTED":
        return TaskStatusResponse(task_id=task_id, status=TaskState.STARTED)
    if state == "SUCCESS":
        payload = result.result if isinstance(result.result, dict) else {"result": result.result}
        if isinstance(payload, dict):
            payload = {**payload, "download_url": f"/tasks/{task_id}/pdf"}
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
    """Download generated PDF. No email required."""
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

    pdf_path_value: str | None = None
    if isinstance(result.result, dict):
        pdf_path_value = result.result.get("pdf_path")

    pdf_path = resolve_pdf_path(task_id, pdf_path_value)
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="PDF file not found for this task.")

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"report_{task_id}.pdf",
    )


@app.exception_handler(AgentError)
async def agent_error_handler(_request, exc: AgentError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message, "agent": exc.agent},
    )
