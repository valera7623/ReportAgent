"""Celery tasks orchestrating the agent pipeline."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import redis

from app.agents.analyst import run_analyst
from app.agents.context_loader import get_user_preferences
from app.agents.formatter import format_report
from app.agents.parser import run_parser
from app.agents.visualizer import run_visualizer
from app.celery_app import celery_app
from app.config.output_formats import EXTERNAL_FORMATS, resolve_output_format
from app.db.database import get_user_by_api_key, update_history_task_result
from app.models.schemas import AgentError
from app.voice.orchestrator import process_voice
from app.voice.storage import delete_voice_file
from app.payments.usage_tracker import check_report_limit, refund_report_slot
from app.utils.logger import get_logger
from app.utils.metrics import report_generation_duration_seconds
from app.webhook.dispatcher import build_webhook_payload, fire_report_webhooks

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


def _send_external_report_email(
    to_email: str,
    *,
    output_format: str,
    external_url: str,
    task_id: str,
) -> None:
    from app.auth.email_service import send_email

    labels = {"notion": "Notion", "google_slides": "Google Slides"}
    label = labels.get(output_format, output_format)
    subject = f"ReportAgent — отчёт в {label}"
    html = f"""
    <html><body>
      <h2>Ваш отчёт готов</h2>
      <p>Отчёт создан в {label}.</p>
      <p><a href="{external_url}">Открыть отчёт</a></p>
      <p>ID задачи: {task_id}</p>
    </body></html>
    """
    if not send_email(to_email, subject, html):
        logger.warning(
            "SMTP not configured or failed; external link for task %s not emailed to %s",
            task_id,
            to_email,
        )


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
        result["file_path"] = str(formatted.file_path)
    if formatted.external_url:
        result["external_url"] = formatted.external_url
    if formatted.pdf_path:
        result["pdf_path"] = str(formatted.pdf_path)
    elif output_format == "pdf" and formatted.file_path:
        result["pdf_path"] = str(formatted.file_path)

    return result


def _resolve_user_id(api_key: str | None) -> str | None:
    if not api_key:
        return None
    user = get_user_by_api_key(api_key)
    return user["id"] if user else None


def _record_history_result(
    user_id: str | None,
    task_id: str,
    *,
    status: str,
    duration_seconds: float,
) -> None:
    if user_id and task_id:
        try:
            update_history_task_result(
                user_id,
                task_id,
                status=status,
                duration_seconds=round(duration_seconds, 2),
            )
        except Exception as exc:
            logger.warning("Failed to update history for task %s: %s", task_id, exc)


def _fire_success_webhooks(
    *,
    task_id: str,
    user_id: str | None,
    result: dict[str, Any],
    source_type: str,
    duration_seconds: float,
) -> None:
    if not user_id:
        return
    payload = build_webhook_payload(
        event="report.completed",
        task_id=task_id,
        status="SUCCESS",
        user_id=user_id,
        output_format=result.get("output_format"),
        download_path=result.get("download_url"),
        source_type=source_type,
        duration_seconds=duration_seconds,
    )
    fire_report_webhooks(
        event="report.completed",
        task_id=task_id,
        user_id=user_id,
        payload=payload,
    )


def _fire_failure_webhooks(
    *,
    task_id: str,
    user_id: str | None,
    error_message: str,
    source_type: str,
    duration_seconds: float,
    output_format: str | None = None,
) -> None:
    if not user_id:
        return
    payload = build_webhook_payload(
        event="report.failed",
        task_id=task_id,
        status="FAILURE",
        user_id=user_id,
        error_message=error_message,
        output_format=output_format,
        source_type=source_type,
        duration_seconds=duration_seconds,
    )
    fire_report_webhooks(
        event="report.failed",
        task_id=task_id,
        user_id=user_id,
        payload=payload,
    )


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
    preview_id: str | None = None,
    ai_suggestions: dict[str, Any] | None = None,
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
        if ai_suggestions:
            parsed["ai_suggestions"] = ai_suggestions
        analyzed = run_analyst(parsed, preferences=prefs)
        if preview_id:
            from app.preview.charts import import_preview_charts

            preview_charts = import_preview_charts(preview_id, task_id)
            if preview_charts:
                visualized = {
                    **analyzed,
                    "chart_paths": preview_charts,
                    "preferences": prefs,
                    "company_logo_url": prefs.get("company_logo_url"),
                }
            else:
                visualized = run_visualizer(analyzed, preferences=prefs)
        else:
            visualized = run_visualizer(analyzed, preferences=prefs)
        charts = visualized.get("chart_paths") or []

        formatted = format_report(
            visualized,
            charts=charts,
            output_format=fmt,
            user_preferences=prefs,
        )

        recipient = email or visualized.get("email")
        result = _build_task_result(
            task_id,
            visualized,
            formatted,
            recipient,
        )
        if recipient and formatted.external_url and fmt in EXTERNAL_FORMATS:
            _send_external_report_email(
                recipient,
                output_format=fmt,
                external_url=formatted.external_url,
                task_id=task_id,
            )
            result["message"] = f"Report link sent to {recipient}"
        return result
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
    preview_id: str | None = None,
    ai_suggestions: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Run context_loader → parser → analyst → visualizer → formatter pipeline."""
    task_id = self.request.id or "unknown"
    logger.info("Task %s started (email=%s, format=%s)", task_id, email or "none", output_format or "default")

    resolved_user_id = user_id or _resolve_user_id(api_key)
    if resolved_user_id and not check_report_limit(resolved_user_id, slot_reserved=True):
        logger.warning("Task %s rejected: report limit exceeded for user %s", task_id, resolved_user_id)
        raise RuntimeError("Report limit exceeded")

    source_type = _source_type_label(sheets_url=sheets_url, file_path=file_path)
    if resolved_user_id and not api_key:
        from app.db.database import get_user_preferences as get_prefs_by_user

        prefs = get_prefs_by_user(resolved_user_id)
    else:
        prefs = get_user_preferences(api_key)
    fmt = resolve_output_format(output_format, prefs)
    started = time.perf_counter()

    if resolved_user_id:
        from app.payments.usage_tracker import get_remaining_reports

        logger.debug(
            "Task %s user %s remaining reports after API consumption: %s",
            task_id,
            resolved_user_id,
            get_remaining_reports(resolved_user_id),
        )

    try:
        result = _run_report_pipeline(
            task_id,
            email=email,
            sheets_url=sheets_url,
            file_path=file_path,
            api_key=api_key,
            output_format=output_format,
            preview_id=preview_id,
            ai_suggestions=ai_suggestions,
            preferences=prefs,
        )
        logger.info("Task %s completed successfully (format=%s)", task_id, result.get("output_format"))
        duration = time.perf_counter() - started
        _record_history_result(resolved_user_id, task_id, status="SUCCESS", duration_seconds=duration)
        _fire_success_webhooks(
            task_id=task_id,
            user_id=resolved_user_id,
            result=result,
            source_type=source_type,
            duration_seconds=duration,
        )
        return result

    except AgentError as exc:
        logger.error("Task %s failed in agent '%s': %s", task_id, exc.agent, exc.message)
        duration = time.perf_counter() - started
        if resolved_user_id and refund_report_slot(user_id=resolved_user_id):
            logger.info("Task %s refunded report slot for user %s", task_id, resolved_user_id)
        _record_history_result(resolved_user_id, task_id, status="FAILURE", duration_seconds=duration)
        _fire_failure_webhooks(
            task_id=task_id,
            user_id=resolved_user_id,
            error_message=f"[{exc.agent}] {exc.message}",
            source_type=source_type,
            duration_seconds=duration,
            output_format=fmt,
        )
        raise RuntimeError(f"[{exc.agent}] {exc.message}") from exc

    except Exception as exc:
        logger.exception("Task %s failed with unexpected error", task_id)
        duration = time.perf_counter() - started
        if resolved_user_id and refund_report_slot(user_id=resolved_user_id):
            logger.info("Task %s refunded report slot for user %s", task_id, resolved_user_id)
        _record_history_result(resolved_user_id, task_id, status="FAILURE", duration_seconds=duration)
        _fire_failure_webhooks(
            task_id=task_id,
            user_id=resolved_user_id,
            error_message=str(exc),
            source_type=source_type,
            duration_seconds=duration,
            output_format=fmt,
        )
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

    resolved_user_id = user_id or _resolve_user_id(api_key)
    if resolved_user_id and not check_report_limit(resolved_user_id, slot_reserved=True):
        logger.warning(
            "Voice task %s rejected: report limit exceeded for user %s",
            task_id,
            resolved_user_id,
        )
        raise RuntimeError("Report limit exceeded")

    source_type = "voice"
    started = time.perf_counter()
    output_fmt: str | None = None

    try:
        prefs = preferences or get_user_preferences(api_key)
        output_fmt = prefs.get("default_output_format")
        if intent and intent.get("output_format"):
            output_fmt = intent["output_format"]

        if transcript is None or intent is None:
            voice_result = process_voice(
                audio_file_path,
                prefs,
                email_override=email,
                user_id=resolved_user_id,
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
                output_fmt = voice_result.intent["output_format"]

        result = _run_report_pipeline(
            task_id,
            email=email,
            sheets_url=sheets_url,
            file_path=file_path,
            api_key=api_key,
            preferences=prefs,
            voice=True,
            output_format=output_fmt,
        )
        result["voice_transcript"] = transcript
        result["voice_intent"] = intent
        logger.info("Voice task %s completed successfully", task_id)
        duration = time.perf_counter() - started
        _record_history_result(resolved_user_id, task_id, status="SUCCESS", duration_seconds=duration)
        _fire_success_webhooks(
            task_id=task_id,
            user_id=resolved_user_id,
            result=result,
            source_type=source_type,
            duration_seconds=duration,
        )
        return result

    except VoiceClarificationError as exc:
        logger.warning("Voice task %s needs clarification: %s", task_id, exc)
        if resolved_user_id and refund_report_slot(user_id=resolved_user_id):
            logger.info("Voice task %s refunded report slot (clarification)", task_id)
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
        duration = time.perf_counter() - started
        if resolved_user_id and refund_report_slot(user_id=resolved_user_id):
            logger.info("Voice task %s refunded report slot for user %s", task_id, resolved_user_id)
        _record_history_result(resolved_user_id, task_id, status="FAILURE", duration_seconds=duration)
        _fire_failure_webhooks(
            task_id=task_id,
            user_id=resolved_user_id,
            error_message=f"[{exc.agent}] {exc.message}",
            source_type=source_type,
            duration_seconds=duration,
            output_format=output_fmt,
        )
        raise RuntimeError(f"[{exc.agent}] {exc.message}") from exc

    except Exception as exc:
        logger.exception("Voice task %s failed with unexpected error", task_id)
        duration = time.perf_counter() - started
        if resolved_user_id and refund_report_slot(user_id=resolved_user_id):
            logger.info("Voice task %s refunded report slot for user %s", task_id, resolved_user_id)
        _record_history_result(resolved_user_id, task_id, status="FAILURE", duration_seconds=duration)
        _fire_failure_webhooks(
            task_id=task_id,
            user_id=resolved_user_id,
            error_message=str(exc),
            source_type=source_type,
            duration_seconds=duration,
            output_format=output_fmt,
        )
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


@celery_app.task(name="tasks.learn_from_failures")
def learn_from_failures() -> dict[str, Any]:
    """
    Hourly task: analyze stale failed fixes and generate LLM candidate solutions.

    Requires OPENAI_API_KEY — otherwise skips LLM generation.
    """
    import json
    import uuid

    from app.self_healing.config import is_self_healing_enabled
    from app.self_healing.vector_store import get_knowledge_base
    from app.voice.config import LLM_MODEL

    if not is_self_healing_enabled():
        return {"status": "skipped", "reason": "self_healing_disabled"}

    kb = get_knowledge_base()
    if kb is None:
        return {"status": "skipped", "reason": "kb_unavailable"}

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.info("learn_from_failures: OPENAI_API_KEY not set — skipping LLM generation")
        return {"status": "skipped", "reason": "no_openai_key"}

    stale = kb.find_stale_failures(min_age_days=7)
    generated = 0

    for record in stale[:10]:
        try:
            from app.voice.openai_client import create_openai_client

            client = create_openai_client()
            prompt = (
                "Вот ошибка и неудачная попытка исправления в data pipeline. "
                "Предложи лучшее техническое решение (без изменения бизнес-логики).\n\n"
                f"Agent: {record.get('agent_name')}\n"
                f"Error: {record.get('error_text', '')[:800]}\n"
                f"Previous prompt: {record.get('solution_prompt', '')}\n"
                f"Previous code: {record.get('solution_code', '')}\n"
                f"Context: {json.dumps(record.get('context') or {}, ensure_ascii=False)[:500]}\n\n"
                'Respond with JSON: {"solution_prompt": "...", "solution_code": "{\\"action\\": ...}"}'
            )
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a DevOps engineer suggesting safe retry fixes for Python data agents. "
                            "JSON only, no eval."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=600,
            )
            content = (response.choices[0].message.content or "").strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            suggestion = json.loads(content)

            kb.add_error(
                {
                    "id": str(uuid.uuid4()),
                    "error_text": record.get("error_text", ""),
                    "error_type": record.get("error_type", "unknown"),
                    "agent_name": record.get("agent_name", "unknown"),
                    "stack_trace": record.get("stack_trace", ""),
                    "solution_prompt": suggestion.get("solution_prompt", ""),
                    "solution_code": suggestion.get("solution_code", ""),
                    "was_successful": False,
                    "success_count": 0,
                    "fail_count": 0,
                    "context": {
                        **(record.get("context") or {}),
                        "source": "learn_from_failures",
                        "parent_id": record.get("id"),
                    },
                }
            )
            generated += 1
            logger.info(
                "Generated candidate fix for stale error %s (agent=%s)",
                record.get("id"),
                record.get("agent_name"),
            )
        except Exception as exc:
            logger.warning("learn_from_failures failed for %s: %s", record.get("id"), exc)

    return {"status": "ok", "stale_count": len(stale), "generated": generated}


@celery_app.task(bind=True, name="tasks.preview_generation")
def preview_generation_task(
    self,
    preview_id: str,
    user_id: str,
    file_path: str | None = None,
    sheets_url: str | None = None,
    api_key: str | None = None,
    ai_suggestions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Async preview generation for large files."""
    from datetime import datetime, timezone

    from app.agents.context_loader import get_user_preferences
    from app.preview.cache import store_job_result, store_preview
    from app.preview.generator import PreviewGenerator
    from app.utils.metrics import record_preview_generated

    job_id = self.request.id or preview_id
    prefs = get_user_preferences(api_key)
    started = datetime.now(timezone.utc)

    try:
        gen = PreviewGenerator()
        result = gen.generate_preview(
            user_id=user_id,
            file_path=file_path,
            sheets_url=sheets_url,
            preferences=prefs,
            preview_id=preview_id,
            ai_suggestions=ai_suggestions,
        )
        cache_payload = result.pop("_cache_payload")
        store_preview(preview_id, cache_payload, user_id)
        duration = (datetime.now(timezone.utc) - started).total_seconds()
        record_preview_generated(duration)

        payload = {
            "status": "ready",
            "preview_id": preview_id,
            "user_id": user_id,
            "data": result["data"],
            "expires_at": result["expires_at"],
        }
        store_job_result(job_id, payload)
        return payload
    except Exception as exc:
        logger.exception("Preview generation failed for %s", preview_id)
        payload = {
            "status": "failed",
            "preview_id": preview_id,
            "user_id": user_id,
            "error": str(exc),
        }
        store_job_result(job_id, payload)
        raise


@celery_app.task(name="tasks.cleanup_previews")
def cleanup_previews() -> dict[str, int]:
    """Remove expired preview cache entries and temp files."""
    from app.preview.cache import cleanup_expired

    removed = cleanup_expired()
    logger.info("Preview cleanup removed %d expired preview(s)", removed)
    return {"removed": removed}


@celery_app.task(name="tasks.run_due_scheduled_reports")
def run_due_scheduled_reports() -> dict[str, int]:
    """Dispatch report generation for schedules whose next_run_at has passed."""
    from app.db.database import get_connection

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dispatched = 0
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, sheets_url, email, output_format, cron_expression
            FROM scheduled_reports
            WHERE enabled = 1 AND next_run_at IS NOT NULL AND next_run_at <= ?
            """,
            (now,),
        ).fetchall()

    for row in rows:
        schedule_id = row["id"]
        user_id = row["user_id"]
        sheets_url = row["sheets_url"]
        if not sheets_url:
            continue
        try:
            from app.payments.usage_tracker import consume_report_slot

            consume_report_slot(user_id=user_id, desired_output_format=row["output_format"])
        except Exception as exc:
            logger.warning("Scheduled report %s skipped (billing): %s", schedule_id, exc)
            continue

        generate_report.delay(
            email=row["email"],
            sheets_url=sheets_url,
            output_format=row["output_format"],
            user_id=user_id,
        )
        dispatched += 1
        next_run = _scheduled_next_run(str(row["cron_expression"]))
        with get_connection() as conn:
            conn.execute(
                """
                UPDATE scheduled_reports
                SET last_run_at = ?, next_run_at = ?
                WHERE id = ?
                """,
                (now, next_run, schedule_id),
            )
    logger.info("Dispatched %d scheduled report(s)", dispatched)
    return {"dispatched": dispatched}


def _scheduled_next_run(cron_expression: str) -> str:
    from app.routers.scheduled_reports import _compute_next_run

    return _compute_next_run(cron_expression)


@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs) -> None:
    """Register Celery Beat schedule for queue length monitoring and self-healing learning."""
    sender.add_periodic_task(
        30.0,
        update_celery_queue_length.s(),
        name="update-celery-queue-length-every-30s",
    )
    sender.add_periodic_task(
        3600.0,
        learn_from_failures.s(),
        name="learn-from-failures-every-hour",
    )
    sender.add_periodic_task(
        600.0,
        cleanup_previews.s(),
        name="cleanup-previews-every-10m",
    )
    sender.add_periodic_task(
        60.0,
        run_due_scheduled_reports.s(),
        name="run-due-scheduled-reports-every-60s",
    )
