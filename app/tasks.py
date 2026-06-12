"""Celery tasks orchestrating the agent pipeline."""

from __future__ import annotations

from typing import Any

from app.agents.analyst import run_analyst
from app.agents.context_loader import get_user_preferences
from app.agents.parser import run_parser
from app.agents.sender import run_sender
from app.agents.visualizer import run_visualizer
from app.celery_app import celery_app
from app.models.schemas import AgentError
from app.voice.orchestrator import process_voice
from app.voice.storage import delete_voice_file
from app.utils.logger import get_logger

logger = get_logger("tasks", "log_tasks.log")


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


def _run_report_pipeline(
    task_id: str,
    *,
    email: str | None,
    sheets_url: str | None,
    file_path: str | None,
    api_key: str | None,
    preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prefs = preferences or get_user_preferences(api_key)

    parsed = run_parser(
        task_id=task_id,
        email=email,
        sheets_url=sheets_url,
        file_path=file_path,
    )
    analyzed = run_analyst(parsed, preferences=prefs)
    visualized = run_visualizer(analyzed, preferences=prefs)
    return run_sender(visualized, preferences=prefs)


@celery_app.task(bind=True, name="tasks.generate_report")
def generate_report(
    self,
    email: str | None = None,
    sheets_url: str | None = None,
    file_path: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Run context_loader → parser → analyst → visualizer → sender pipeline."""
    task_id = self.request.id or "unknown"
    logger.info("Task %s started (email=%s)", task_id, email or "none")

    try:
        result = _run_report_pipeline(
            task_id,
            email=email,
            sheets_url=sheets_url,
            file_path=file_path,
            api_key=api_key,
        )
        logger.info("Task %s completed successfully", task_id)
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

        result = _run_report_pipeline(
            task_id,
            email=email,
            sheets_url=sheets_url,
            file_path=file_path,
            api_key=api_key,
            preferences=prefs,
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
