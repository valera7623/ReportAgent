"""LLM-based intent extraction from transcribed voice text."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from app.voice.config import LLM_MODEL
from app.utils.logger import get_logger

logger = get_logger("voice_intent_parser", "log_voice.log")

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

SYSTEM_PROMPT = """Ты — intent parser для генерации отчётов. Из текста пользователя извлеки:
- source_type: "file" или "sheets_url" (если упомянут Google Sheets или ссылка)
- source_value: URL если sheets_url, или null (файл будет загружен отдельно)
- chart_type: "bar", "line", "pie" (если пользователь явно сказал, иначе null)
- metrics: список колонок или метрик для анализа (например ["sales", "profit"])
- group_by: колонка для группировки (например "month", "category")
- target_email: email получателя (если есть)
- missing_info: список того, чего не хватает (например ["source_type", "metrics"])

Верни JSON. Если информации мало — заполни missing_info и верни частичный результат.
Всегда включай все перечисленные ключи в JSON."""


def _extract_email_regex(text: str) -> str | None:
    match = EMAIL_RE.search(text)
    return match.group(0) if match else None


def parse_intent(text: str, user_preferences: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Parse user intent from transcript using GPT JSON mode.

    Merges defaults from user_preferences (preferred_chart_type, default_email).
    """
    prefs = user_preferences or {}
    default_chart = prefs.get("preferred_chart_type", "bar")
    default_email = prefs.get("default_email")

    if not text.strip():
        return {
            "source_type": None,
            "source_value": None,
            "chart_type": default_chart,
            "metrics": [],
            "group_by": None,
            "target_email": default_email,
            "missing_info": ["transcript", "source_type"],
            "raw_transcript": text,
        }

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.error("OPENAI_API_KEY not configured; intent parsing skipped")
        return _fallback_intent(text, default_chart, default_email)

    user_hint = (
        f"User preferences hint: preferred_chart_type={default_chart}, "
        f"default_email={default_email or 'none'}"
    )

    try:
        from app.voice.openai_client import create_openai_client

        client = create_openai_client()
        response = client.chat.completions.create(
            model=LLM_MODEL(),
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{user_hint}\n\nUser said:\n{text}"},
            ],
            temperature=0.1,
        )
        raw = response.choices[0].message.content or "{}"
        logger.info("LLM raw intent response: %s", raw[:500])

        parsed = json.loads(raw)
        intent = _normalize_intent(parsed, text, default_chart, default_email)
        logger.info("Parsed intent: %s", json.dumps(intent, ensure_ascii=False)[:500])
        return intent

    except Exception as exc:
        logger.exception("Intent parsing failed: %s", exc)
        return _fallback_intent(text, default_chart, default_email)


def _normalize_intent(
    parsed: dict[str, Any],
    transcript: str,
    default_chart: str,
    default_email: str | None,
) -> dict[str, Any]:
    email = parsed.get("target_email") or _extract_email_regex(transcript) or default_email
    chart = parsed.get("chart_type") or default_chart

    source_type = parsed.get("source_type")
    source_value = parsed.get("source_value")

    if source_type == "sheets_url" and source_value:
        url = str(source_value).strip()
        if "docs.google.com/spreadsheets" in url or url.startswith("http"):
            source_value = url
        else:
            parsed.setdefault("missing_info", []).append("source_value")

    metrics = parsed.get("metrics") or []
    if isinstance(metrics, str):
        metrics = [metrics]

    missing = list(parsed.get("missing_info") or [])
    if not source_type and "source_type" not in missing:
        missing.append("source_type")
    if source_type == "sheets_url" and not source_value and "source_value" not in missing:
        missing.append("source_value")
    if source_type == "file" and "file_upload" not in missing:
        missing.append("file_upload")

    return {
        "source_type": source_type,
        "source_value": source_value,
        "chart_type": chart,
        "metrics": metrics,
        "group_by": parsed.get("group_by"),
        "target_email": email,
        "missing_info": missing,
        "raw_transcript": transcript,
    }


def _fallback_intent(text: str, default_chart: str, default_email: str | None) -> dict[str, Any]:
    url_match = re.search(r"https?://\S+", text)
    source_type = "sheets_url" if url_match else None
    source_value = url_match.group(0).rstrip(".,)") if url_match else None

    missing = []
    if not source_type:
        missing.append("source_type")

    return {
        "source_type": source_type,
        "source_value": source_value,
        "chart_type": default_chart,
        "metrics": [],
        "group_by": None,
        "target_email": _extract_email_regex(text) or default_email,
        "missing_info": missing,
        "raw_transcript": text,
    }


def merge_clarification_answer(partial_intent: dict[str, Any], answer: str) -> str:
    """Combine original transcript with user's clarification for re-parsing."""
    original = partial_intent.get("raw_transcript") or ""
    return f"{original}\n\nClarification: {answer}".strip()
