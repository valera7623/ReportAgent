"""AI analysis and AI-assisted report generation endpoints."""

from __future__ import annotations

import json
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, EmailStr

from app.agents.context_loader import get_user_preferences
from app.agents.parser import load_dataframe, save_upload, validate_request
from app.config.output_formats import resolve_output_format, validate_format_credentials
from app.db.ai_suggestions import save_ai_suggestions
from app.db.database import log_history, resolve_email_for_user
from app.models.schemas import AgentError, GenerateReportResponse
from app.payments.usage_tracker import consume_report_slot
from app.services.ai_enhancer import get_ai_enhancer
from app.tasks import generate_report
from app.utils.logger import get_logger

logger = get_logger("ai_enhancer_router", "log_api.log")

router = APIRouter(tags=["AI Enhancer"])


class GenerateWithAIForm(BaseModel):
    email: EmailStr | None = None
    output_format: str | None = None
    accept_suggestions: bool = True
    suggestions_json: str | None = None


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return user_id


def _api_key(request: Request) -> str | None:
    return getattr(request.state, "api_key", None)


async def _load_source(
    *,
    file: UploadFile | None,
    sheets_url: str | None,
) -> tuple[Any, str, bytes | None]:
    """Return (dataframe, file_hash, optional saved path)."""
    enhancer = get_ai_enhancer()
    saved_path: str | None = None

    if file and file.filename:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        file_hash = enhancer.hash_bytes(content)
        dest = save_upload(content, file.filename)
        saved_path = str(dest)
        df = load_dataframe(file_path=dest)
        return df, file_hash, saved_path

    if sheets_url:
        df = load_dataframe(sheets_url=sheets_url.strip())
        file_hash = enhancer._generate_hash(df.head(enhancer.max_rows))
        return df, file_hash, None

    raise HTTPException(status_code=400, detail="Provide file or sheets_url")


@router.post("/api/reports/analyze")
async def analyze_report_data(
    request: Request,
    sheets_url: Annotated[str | None, Form()] = None,
    file: UploadFile | None = File(default=None),
) -> dict[str, Any]:
    """Analyze uploaded data and return AI/heuristic recommendations."""
    user_id = _require_user_id(request)
    has_file = file is not None and bool(file.filename)
    url = (sheets_url or "").strip() or None

    try:
        validate_request(None, url, has_file)
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    enhancer = get_ai_enhancer()
    df, file_hash, _saved = await _load_source(file=file, sheets_url=url)

    suggestions = enhancer.analyze_dataframe(df, file_hash=file_hash)
    was_cached = bool(suggestions.pop("cached", False))

    try:
        save_ai_suggestions(user_id, file_hash, suggestions)
    except Exception as exc:
        logger.warning("Could not persist ai_suggestions to DB: %s", exc)

    return {
        **suggestions,
        "cached": was_cached,
        "ai_enabled": enhancer.enabled,
    }


@router.post("/api/reports/generate-with-ai", response_model=GenerateReportResponse)
async def generate_report_with_ai(
    request: Request,
    sheets_url: Annotated[str | None, Form()] = None,
    email: Annotated[str | None, Form()] = None,
    output_format: Annotated[str | None, Form()] = None,
    accept_suggestions: Annotated[bool, Form()] = True,
    suggestions_json: Annotated[str | None, Form()] = None,
    file: UploadFile | None = File(default=None),
) -> GenerateReportResponse:
    """Queue report generation using AI chart/column recommendations."""
    user_id = _require_user_id(request)
    api_key = _api_key(request)
    has_file = file is not None and bool(file.filename)
    url = (sheets_url or "").strip() or None

    try:
        validate_request(email, url, has_file)
    except AgentError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    enhancer = get_ai_enhancer()
    df, file_hash, saved_path = await _load_source(file=file, sheets_url=url)

    ai_suggestions: dict[str, Any] | None = None
    if accept_suggestions:
        if suggestions_json:
            try:
                ai_suggestions = json.loads(suggestions_json)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail="Invalid suggestions_json") from exc
        else:
            ai_suggestions = enhancer.analyze_dataframe(df, file_hash=file_hash)
            ai_suggestions.pop("cached", None)

        try:
            save_ai_suggestions(user_id, file_hash, ai_suggestions)
        except Exception as exc:
            logger.warning("Could not persist ai_suggestions: %s", exc)

    prefs = get_user_preferences(api_key)
    resolved_format = resolve_output_format(output_format, prefs)
    validate_format_credentials(resolved_format)

    email_clean = resolve_email_for_user(user_id, email, prefs)

    usage_count = 0
    if user_id:
        slot = consume_report_slot(user_id=user_id, desired_output_format=resolved_format)
        usage_count = slot.used_reports

    task_kwargs: dict[str, Any] = {
        "email": email_clean,
        "sheets_url": url,
        "file_path": saved_path,
        "api_key": api_key,
        "output_format": resolved_format,
        "ai_suggestions": ai_suggestions,
    }

    result = generate_report.apply_async(kwargs=task_kwargs, task_id=str(uuid.uuid4()))
    task_id = result.id

    log_history(
        user_id,
        f"POST /api/reports/generate-with-ai format={resolved_format} ai={accept_suggestions}",
        task_id,
        request_type="ai",
        output_format=resolved_format,
    )

    download_url = (
        f"/tasks/{task_id}/pdf"
        if resolved_format == "pdf"
        else f"/tasks/{task_id}/export"
    )

    return GenerateReportResponse(
        task_id=task_id,
        status="queued",
        message=f"AI-assisted report generation started ({resolved_format}).",
        download_url=download_url,
        output_format=resolved_format,
        user_id=user_id,
        usage_count=usage_count,
    )
