"""Celery tasks orchestrating the agent pipeline."""

from __future__ import annotations

import os
import time
from typing import Any

import redis

from app.agents.analyst import run_analyst
from app.agents.context_loader import get_user_preferences
from app.agents.formatter import format_report
from app.agents.parser import run_parser
from app.agents.visualizer import run_visualizer
from app.celery_app import celery_app
from app.config.output_formats import EXTERNAL_FORMATS, resolve_output_format
from app.models.schemas import AgentError
from app.voice.orchestrator import process_voice
from app.voice.storage import delete_voice_file
from app.utils.logger import get_logger
from app.utils.metrics import report_generation_duration_seconds

logger = get_logger("tasks", "log_tasks.log")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CELERY_QUEUE_KEY = os.getenv("CELERY_QUEUE_NAME", "celery")
METRICS_QUEUE_REDIS_KEY = "metrics:celery_queue_length"


class VoiceClarificationError(Exception):
    """Raised when voice pipeline cannot proceed without user clarification."""

    def __init__(
        self,
        message: str,
        *,
        partial_intent: dict[str, Any],
        clarification_question: str,
        transcript: str = "",
    ) -> None:
        super().__init__(message)
        self.partial_intent = partial_intent
        self.clarification_question = clarification_question
        self.transcript = transcript


def _source_type_label(
    *,
    sheets_url: str | None,
    file_path: str | None,
    voice: bool = False,
) -> str:
    if voice:
        return "voice"
    if file_path:
        return "file"
    if sheets_url:
        return "sheets"
    return "unknown"


def _build_task_result(
    task_id: str,
    visualized: dict[str, Any],
    formatted,
    email: str | None,
) -> dict[str, Any]:
    """Merge formatter output into Celery task result dict."""
    output_format = formatted.output_format
    chart_count = len(visualized.get("chart_paths") or [])

    if output_format in EXTERNAL_FORMATS:
        message = f"Report generated as {output_format}. Open external_url."
        download_url = f"/tasks/{task_id}/export"
    elif output_format == "pdf":
        message = (
            f"Report generated and sent to {email}"
            if email
            else "Report generated. Download via GET /tasks/{task_id}/pdf"
        )
        download_url = f"/tasks/{task_id}/pdf"
    else:
        message = f"Report generated as {output_format}. Download via GET /tasks/{task_id}/export"
        download_url = f"/tasks/{task_id}/export"

    result: dict[str, Any] = {
        "task_id": task_id,
        "email": email or visualized.get("email"),
        "chart_count": chart_count,
        "status": "completed",
        "message": message,
        "output_format": output_format,
        "content_type": formatted.content_type,
        "download_url": download_url,
    }

    if formatted.file_path:
        result["file_path"] = formatted.file_path
    if formatted.external_url:
        result["external_url"] = formatted.external_url
    if formatted.pdf_path:
        result["pdf_path"] = formatted.pdf_path
    elif output_format == "pdf" and formatted.file_path:
        result["pdf_path"] = formatted.file_path

    return result


def _run_report_pipeline(
    task_id: str,
    *,
    email: str | None,
    sheets_url: str | None,
    file_path: str | None,
    api_key: str | None,
    preferences: dict[str, Any] | None = None,
    voice: bool = False,
    output_format: str | None = None,
) -> dict[str, Any]:
    prefs = preferences or get_user_preferences(api_key)
    fmt = resolve_output_format(output_format, prefs)
    source_type = _source_type_label(
        sheets_url=sheets_url,
        file_path=file_path,
        voice=voice,
    )
    started = time.perf_counter()

    try:
        parsed = run_parser(
            task_id=task_id,
            email=email,
            sheets_url=sheets_url,
            file_path=file_path,
        )
        analyzed = run_analyst(parsed, preferences=prefs)
        visualized = run_visualizer(analyzed, preferences=prefs)
        charts = visualized.get("chart_paths") or []

        formatted = format_report(
            visualized,
            charts=charts,
            output_format=fmt,
            user_preferences=prefs,
        )

        return _build_task_result(
            task_id,
            visualized,
            formatted,
            email or visualized.get("email"),
        )
    finally:
        report_generation_duration_seconds.labels(source_type=source_type).observe(
            time.perf_counter() - started
        )


@celery_app.task(bind=True, name="tasks.generate_report")
def generate_report(
    self,
    email: str | None = None,
    sheets_url: str | None = None,
    file_path: str | None = None,
    api_key: str | None = None,
    output_format: str | None = None,
) -> dict[str, Any]:
    """Run context_loader → parser → analyst → visualizer → formatter pipeline."""
    task_id = self.request.id or "unknown"
    logger.info("Task %s started (email=%s, format=%s)", task_id, email or "none", output_format or "default")

    try:
        result = _run_report_pipeline(
            task_id,
            email=email,
            sheets_url=sheets_url,
            file_path=file_path,
            api_key=api_key,
            output_format=output_format,
        )
        logger.info("Task %s completed successfully (format=%s)", task_id, result.get("output_format"))
        return result

    except AgentError as exc:
        logger.error("Task %s failed in agent '%s': %s", task_id, exc.agent, exc.message)
        raise RuntimeError(f"[{exc.agent}] {exc.message}") from exc

    except Exception as exc:
        logger.exception("Task %s failed with unexpected error", task_id)
        raise


@celery_app.task(bind=True, name="tasks.generate_voice_report")
def generate_voice_report(
    self,
    audio_file_path: str,
    email: str | None = None,
    user_id: str | None = None,
    api_key: str | None = None,
    sheets_url: str | None = None,
    file_path: str | None = None,
    transcript: str | None = None,
    intent: dict[str, Any] | None = None,
    preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Voice report task: optional re-transcription, then standard report pipeline.

    When transcript/intent are pre-computed by the API layer, skips Whisper/LLM.
    """
    task_id = self.request.id or "unknown"
    logger.info("Voice task %s started (user=%s)", task_id, user_id or "anon")

    try:
        prefs = preferences or get_user_preferences(api_key)
        output_format = prefs.get("default_output_format")
        if intent and intent.get("output_format"):
            output_format = intent["output_format"]

        if transcript is None or intent is None:
            voice_result = process_voice(
                audio_file_path,
                prefs,
                email_override=email,
                user_id=user_id,
            )
            if voice_result.status == "needs_clarification":
                raise VoiceClarificationError(
                    voice_result.clarification_question or "Clarification required",
                    partial_intent=voice_result.intent,
                    clarification_question=voice_result.clarification_question or "",
                    transcript=voice_result.transcript,
                )
            email = voice_result.email
            sheets_url = voice_result.sheets_url
            file_path = voice_result.file_path
            prefs = voice_result.preferences
            if voice_result.intent.get("output_format"):
                output_format = voice_result.intent["output_format"]

        result = _run_report_pipeline(
            task_id,
            email=email,
            sheets_url=sheets_url,
            file_path=file_path,
            api_key=api_key,
            preferences=prefs,
            voice=True,
            output_format=output_format,
        )
        result["voice_transcript"] = transcript
        result["voice_intent"] = intent
        logger.info("Voice task %s completed successfully", task_id)
        return result

    except VoiceClarificationError as exc:
        logger.warning("Voice task %s needs clarification: %s", task_id, exc)
        self.update_state(
            state="NEEDS_CLARIFICATION",
            meta={
                "partial_intent": exc.partial_intent,
                "clarification_question": exc.clarification_question,
                "transcript": exc.transcript,
            },
        )
        raise RuntimeError(exc.clarification_question) from exc

    except AgentError as exc:
        logger.error("Voice task %s failed in agent '%s': %s", task_id, exc.agent, exc.message)
        raise RuntimeError(f"[{exc.agent}] {exc.message}") from exc

    except Exception as exc:
        logger.exception("Voice task %s failed with unexpected error", task_id)
        raise

    finally:
        delete_voice_file(audio_file_path)


@celery_app.task(name="tasks.update_celery_queue_length")
def update_celery_queue_length() -> dict[str, int]:
    """Periodic task: publish Celery queue length to Redis for FastAPI /metrics."""
    client = redis.from_url(REDIS_URL, decode_responses=True)
    length = int(client.llen(CELERY_QUEUE_KEY))
    client.set(METRICS_QUEUE_REDIS_KEY, length, ex=120)
    logger.debug("Celery queue length: %d", length)
    return {"queue_length": length}


@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    """Register Celery Beat schedule for queue length monitoring."""
    sender.add_periodic_task(
        30.0,
        update_celery_queue_length.s(),
        name="update-celery-queue-length-every-30s",
    )
