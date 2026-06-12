"""Voice pipeline: transcription → intent → report parameters."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from app.db.database import resolve_email_for_user
from app.voice.intent_parser import merge_clarification_answer, parse_intent
from app.voice.transcriber import transcribe_audio
from app.utils.logger import get_logger

logger = get_logger("voice_orchestrator", "log_voice.log")

CRITICAL_MISSING = frozenset({"source_type", "source_value", "file_upload", "transcript"})


@dataclass
class VoiceProcessResult:
    status: Literal["ready", "needs_clarification", "failed"]
    transcript: str
    intent: dict[str, Any]
    email: str | None
    sheets_url: str | None
    file_path: str | None
    preferences: dict[str, Any]
    clarification_question: str | None = None
    duration_seconds: float | None = None
    confidence: float | None = None
    error: str | None = None


def _build_clarification_question(intent: dict[str, Any]) -> str:
    missing = intent.get("missing_info") or []
    if "transcript" in missing or not intent.get("raw_transcript"):
        return "Не удалось распознать речь. Повторите запрос чётче или укажите текстом источник данных."
    if "file_upload" in missing:
        return (
            "Вы хотите отчёт по файлу, но голосом файл не передаётся. "
            "Укажите публичную ссылку на Google Sheets или загрузите CSV через POST /generate_report."
        )
    if "source_value" in missing or "source_type" in missing:
        return (
            "Не указан источник данных. Скажите ссылку на Google Sheets "
            "или уточните, какие данные анализировать."
        )
    if "metrics" in missing:
        return "Какие метрики или колонки нужно проанализировать? Например: sales, profit."
    return "Уточните, пожалуйста, источник данных и тип отчёта."


def _needs_clarification(intent: dict[str, Any]) -> bool:
    missing = set(intent.get("missing_info") or [])
    if missing & CRITICAL_MISSING:
        return True
    source_type = intent.get("source_type")
    if source_type == "file":
        return True
    if source_type == "sheets_url" and not intent.get("source_value"):
        return True
    if not source_type:
        return True
    return False


def _merge_preferences(user_preferences: dict[str, Any], intent: dict[str, Any]) -> dict[str, Any]:
    prefs = dict(user_preferences)
    if intent.get("chart_type"):
        prefs["preferred_chart_type"] = intent["chart_type"]
    extra = dict(prefs.get("extra") or {})
    if intent.get("metrics"):
        extra["voice_metrics"] = intent["metrics"]
    if intent.get("group_by"):
        extra["voice_group_by"] = intent["group_by"]
    prefs["extra"] = extra
    prefs["voice_intent"] = intent
    return prefs


def process_voice(
    audio_path: str,
    user_preferences: dict[str, Any],
    *,
    email_override: str | None = None,
    user_id: str | None = None,
    existing_transcript: str | None = None,
    existing_intent: dict[str, Any] | None = None,
) -> VoiceProcessResult:
    """Run transcription and intent parsing; return ready state or clarification needs."""
    if existing_intent is not None and existing_transcript is not None:
        transcript = existing_transcript
        intent = existing_intent
        duration = None
        confidence = None
    else:
        tx = transcribe_audio(audio_path)
        transcript = tx["text"]
        duration = tx.get("duration_seconds")
        confidence = tx.get("confidence")
        intent = parse_intent(transcript, user_preferences)

    email = email_override or intent.get("target_email")
    if user_id and not email:
        email = resolve_email_for_user(user_id, None)
    elif email_override:
        email = email_override

    preferences = _merge_preferences(user_preferences, intent)

    if not transcript.strip():
        intent.setdefault("missing_info", []).append("transcript")
        return VoiceProcessResult(
            status="needs_clarification",
            transcript=transcript,
            intent=intent,
            email=email,
            sheets_url=None,
            file_path=None,
            preferences=preferences,
            clarification_question=_build_clarification_question(intent),
            duration_seconds=duration,
            confidence=confidence,
        )

    if _needs_clarification(intent):
        return VoiceProcessResult(
            status="needs_clarification",
            transcript=transcript,
            intent=intent,
            email=email,
            sheets_url=None,
            file_path=None,
            preferences=preferences,
            clarification_question=_build_clarification_question(intent),
            duration_seconds=duration,
            confidence=confidence,
        )

    sheets_url = None
    file_path = None
    if intent.get("source_type") == "sheets_url":
        sheets_url = intent.get("source_value")

    return VoiceProcessResult(
        status="ready",
        transcript=transcript,
        intent=intent,
        email=email,
        sheets_url=sheets_url,
        file_path=file_path,
        preferences=preferences,
        duration_seconds=duration,
        confidence=confidence,
    )


def reprocess_with_clarification(
    partial_state: dict[str, Any],
    answer: str,
    user_preferences: dict[str, Any],
) -> VoiceProcessResult:
    """Re-parse intent after user clarification."""
    combined = merge_clarification_answer(
        partial_state.get("partial_intent") or {"raw_transcript": partial_state.get("transcript", "")},
        answer,
    )
    intent = parse_intent(combined, user_preferences)
    return process_voice(
        partial_state["audio_path"],
        user_preferences,
        email_override=partial_state.get("email"),
        user_id=partial_state.get("user_id"),
        existing_transcript=combined,
        existing_intent=intent,
    )


def new_clarification_task_id() -> str:
    return f"voice-{uuid.uuid4().hex}"
