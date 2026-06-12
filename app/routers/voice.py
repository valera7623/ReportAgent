"""Voice report generation endpoints."""

from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.agents.context_loader import get_user_preferences
from app.db.database import get_usage_count, log_history, resolve_email_for_user
from app.tasks import generate_report, generate_voice_report
from app.voice.config import voice_available, voice_enabled
from app.voice.models import VoiceClarifyRequest, VoiceClarifyResponse, VoiceGenerateReportResponse
from app.voice.orchestrator import new_clarification_task_id, process_voice, reprocess_with_clarification
from app.voice.redis_store import delete_partial_state, load_partial_state, mark_queued, save_partial_state
from app.voice.storage import delete_voice_file, save_voice_upload
from app.utils.logger import get_logger

logger = get_logger("voice_router", "log_voice.log")

router = APIRouter(prefix="/voice", tags=["Voice"])


def _require_voice() -> None:
    if not voice_enabled():
        raise HTTPException(status_code=501, detail="Voice input is disabled (VOICE_ENABLED=false)")
    if not voice_available():
        raise HTTPException(
            status_code=501,
            detail="Voice input requires OPENAI_API_KEY to be configured",
        )


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return user_id


def _log_voice_transaction(
    user_id: str,
    task_id: str,
    transcript: str,
    intent: dict,
    *,
    success: bool,
    error: str | None = None,
    duration: float | None = None,
) -> None:
    preview = transcript[:80] if transcript else ""
    summary = f"voice: {preview}" if success else f"voice_error: {error or 'unknown'}"
    log_history(user_id, summary, task_id, request_type="voice")
    logger.info(
        "Voice transaction user=%s task=%s success=%s duration=%s intent=%s error=%s",
        user_id,
        task_id,
        success,
        duration,
        json.dumps(intent, ensure_ascii=False)[:300],
        error,
    )


@router.post("/generate_report", response_model=VoiceGenerateReportResponse, status_code=202)
async def voice_generate_report(
    request: Request,
    audio: UploadFile = File(..., description="Voice message (mp3, wav, m4a, ogg)"),
    email: Annotated[str | None, Form(description="Optional recipient email override")] = None,
) -> VoiceGenerateReportResponse:
    """
    Generate a report from a voice message.

    Transcribes audio, parses intent, and either queues report generation
    or returns a clarification question with task_id for follow-up.
    """
    _require_voice()
    user_id = _require_user_id(request)
    api_key = getattr(request.state, "api_key", None)
    email_clean = email.strip() if email else None
    if user_id:
        email_clean = resolve_email_for_user(user_id, email_clean)

    content = await audio.read()
    audio_path: str | None = None

    try:
        saved = save_voice_upload(content, audio.filename or "voice.wav")
        audio_path = str(saved)

        preferences = get_user_preferences(api_key)
        result = process_voice(
            audio_path,
            preferences,
            email_override=email_clean,
            user_id=user_id,
        )

        usage_count = get_usage_count(user_id) + 1

        if result.status == "needs_clarification":
            task_id = new_clarification_task_id()
            save_partial_state(
                task_id,
                user_id=user_id,
                api_key=api_key,
                audio_path=audio_path,
                transcript=result.transcript,
                partial_intent=result.intent,
                clarification_question=result.clarification_question or "",
                email=result.email,
            )
            _log_voice_transaction(
                user_id,
                task_id,
                result.transcript,
                result.intent,
                success=False,
                error="needs_clarification",
                duration=result.duration_seconds,
            )
            return VoiceGenerateReportResponse(
                task_id=task_id,
                status="needs_clarification",
                message=result.clarification_question or "Additional information required.",
                transcript=result.transcript,
                intent=result.intent,
                clarification_question=result.clarification_question,
                partial_intent=result.intent,
                user_id=user_id,
                usage_count=usage_count,
                transcription_error=result.transcription_error,
            )

        celery_task = generate_voice_report.delay(
            audio_file_path=audio_path,
            email=result.email,
            user_id=user_id,
            api_key=api_key,
            sheets_url=result.sheets_url,
            file_path=result.file_path,
            transcript=result.transcript,
            intent=result.intent,
            preferences=result.preferences,
        )
        mark_queued(celery_task.id)

        _log_voice_transaction(
            user_id,
            celery_task.id,
            result.transcript,
            result.intent,
            success=True,
            duration=result.duration_seconds,
        )

        return VoiceGenerateReportResponse(
            task_id=celery_task.id,
            status="queued",
            message="Voice request accepted. Report generation started.",
            transcript=result.transcript,
            intent=result.intent,
            download_url=f"/tasks/{celery_task.id}/pdf",
            user_id=user_id,
            usage_count=usage_count,
        )

    except ValueError as exc:
        delete_voice_file(audio_path)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        delete_voice_file(audio_path)
        raise
    except Exception as exc:
        delete_voice_file(audio_path)
        logger.exception("Voice generate_report failed")
        raise HTTPException(status_code=500, detail=f"Voice processing failed: {exc}") from exc


@router.post("/clarify", response_model=VoiceClarifyResponse, status_code=202)
async def voice_clarify(request: Request, body: VoiceClarifyRequest) -> VoiceClarifyResponse:
    """Provide clarification for a voice request that needs more information."""
    _require_voice()
    user_id = _require_user_id(request)

    partial = load_partial_state(body.task_id)
    if partial is None:
        raise HTTPException(status_code=404, detail="Voice clarification session not found or expired")

    if partial.get("user_id") and partial["user_id"] != user_id:
        raise HTTPException(status_code=403, detail="This clarification session belongs to another user")

    api_key = partial.get("api_key") or getattr(request.state, "api_key", None)
    preferences = get_user_preferences(api_key)
    audio_path = partial["audio_path"]

    try:
        result = reprocess_with_clarification(partial, body.answer, preferences)

        if result.status == "needs_clarification":
            save_partial_state(
                body.task_id,
                user_id=user_id,
                api_key=api_key,
                audio_path=audio_path,
                transcript=result.transcript,
                partial_intent=result.intent,
                clarification_question=result.clarification_question or "",
                email=result.email,
            )
            _log_voice_transaction(
                user_id,
                body.task_id,
                result.transcript,
                result.intent,
                success=False,
                error="needs_clarification",
            )
            return VoiceClarifyResponse(
                task_id=body.task_id,
                status="needs_clarification",
                message=result.clarification_question or "Still need more information.",
                clarification_question=result.clarification_question,
                partial_intent=result.intent,
            )

        delete_partial_state(body.task_id)

        celery_task = generate_voice_report.delay(
            audio_file_path=audio_path,
            email=result.email,
            user_id=user_id,
            api_key=api_key,
            sheets_url=result.sheets_url,
            file_path=result.file_path,
            transcript=result.transcript,
            intent=result.intent,
            preferences=result.preferences,
        )
        mark_queued(celery_task.id)

        _log_voice_transaction(
            user_id,
            celery_task.id,
            result.transcript,
            result.intent,
            success=True,
        )

        return VoiceClarifyResponse(
            task_id=celery_task.id,
            status="queued",
            message="Clarification accepted. Report generation started.",
            download_url=f"/tasks/{celery_task.id}/pdf",
        )

    except Exception as exc:
        logger.exception("Voice clarify failed for task %s", body.task_id)
        raise HTTPException(status_code=500, detail=f"Clarification processing failed: {exc}") from exc
