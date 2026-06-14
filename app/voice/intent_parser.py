"""LLM-based intent extraction from transcribed voice text."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from app.voice.config import LLM_MODEL
from app.utils.logger import get_logger
from app.utils.metrics import track_agent_metrics

logger = get_logger("voice_intent_parser", "log_voice.log")

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

_SPOKEN_AT_PATTERNS = (
    (re.compile(r"(\b[\w.-]+)sobaka(\.[\w.-]+\b)", re.I), r"\1@\2"),
    (re.compile(r"(\b[\w.-]+)собака(\.[\w.-]+\b)", re.I), r"\1@\2"),
    (re.compile(r"(\b[\w.-]+)\s+at\s+(\.[\w.-]+\b)", re.I), r"\1@\2"),
    (re.compile(r"(\b[\w.-]+)\s+собака\s+(\.[\w.-]+\b)", re.I), r"\1@\2"),
)

SYSTEM_PROMPT = """Ты — intent parser для генерации отчётов. Из текста пользователя извлеки:
- source_type: "file" или "sheets_url" (если упомянут Google Sheets или ссылка)
- source_value: URL если sheets_url, или null (файл будет загружен отдельно)
- chart_type: "bar", "line", "pie" (если пользователь явно сказал, иначе null)
- metrics: список колонок или метрик для анализа (например ["sales", "profit"])
- group_by: колонка для группировки (например "month", "category")
- target_email: email получателя (если есть)
- output_format: формат вывода — "pdf", "excel", "pptx", "notion", "google_slides" (если явно указан, иначе null)
- missing_info: список того, чего не хватает (например ["source_type", "metrics"])

Примеры output_format:
- "сделай в Excel", "эксель" → "excel"
- "отправь в Notion", "в ноушен" → "notion"
- "создай презентацию", "powerpoint", "pptx" → "pptx"
- "google slides", "гугл презентацию" → "google_slides"
- "pdf", "пдф" → "pdf"

Если email произнесён как "sobaka" или "собака" вместо @ — верни нормальный email с @.
"график по месяцам" / "динамика" → chart_type "line"; "круговая" → "pie"; иначе null.

Верни JSON. Если информации мало — заполни missing_info и верни частичный результат.
Всегда включай все перечисленные ключи в JSON."""


def normalize_spoken_email(text: str) -> str:
    """Fix common speech-to-text email artifacts before parsing."""
    result = text
    for pattern, repl in _SPOKEN_AT_PATTERNS:
        result = pattern.sub(repl, result)
    return result


def _extract_email_regex(text: str) -> str | None:
    normalized = normalize_spoken_email(text)
    match = EMAIL_RE.search(normalized)
    return match.group(0) if match else None


def _normalize_email_value(email: str | None) -> str | None:
    if not email:
        return None
    normalized = normalize_spoken_email(str(email))
    match = EMAIL_RE.search(normalized)
    return match.group(0) if match else normalized if "@" in normalized else email


@track_agent_metrics("intent_parser")
def parse_intent(text: str, user_preferences: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse user intent from transcript using GPT JSON mode."""
    prefs = user_preferences or {}
    default_chart = prefs.get("preferred_chart_type", "bar")
    default_email = prefs.get("default_email")
    default_format = prefs.get("default_output_format", "pdf")
    text = normalize_spoken_email(text)

    if not text.strip():
        return {
            "source_type": None,
            "source_value": None,
            "chart_type": default_chart,
            "metrics": [],
            "group_by": None,
            "target_email": default_email,
            "output_format": default_format,
            "missing_info": ["transcript", "source_type"],
            "raw_transcript": text,
        }

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.error("OPENAI_API_KEY not configured; intent parsing skipped")
        return _fallback_intent(text, default_chart, default_email, default_format)

    user_hint = (
        f"User preferences hint: preferred_chart_type={default_chart}, "
        f"default_email={default_email or 'none'}, "
        f"default_output_format={default_format}"
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
        intent = _normalize_intent(parsed, text, default_chart, default_email, default_format)
        logger.info("Parsed intent: %s", json.dumps(intent, ensure_ascii=False)[:500])
        return intent

    except Exception as exc:
        logger.exception("Intent parsing failed: %s", exc)
        return _fallback_intent(text, default_chart, default_email, default_format)


_OUTPUT_FORMAT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "excel": ("excel", "эксель", "xlsx", "таблиц"),
    "notion": ("notion", "ноушен", "ноушн"),
    "pptx": ("презентац", "powerpoint", "pptx", "ppt", "слайд"),
    "google_slides": ("google slides", "гугл слайд", "гугл презентац", "google_slides"),
    "pdf": ("pdf", "пдф"),
}


def _infer_output_format(transcript: str, parsed_format: str | None) -> str | None:
    if parsed_format in ("pdf", "excel", "pptx", "notion", "google_slides"):
        return parsed_format
    lower = transcript.lower()
    for fmt, keywords in _OUTPUT_FORMAT_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return fmt
    return None


def _infer_chart_type(transcript: str, parsed_chart: str | None, default: str) -> str:
    if parsed_chart in ("bar", "line", "pie"):
        return parsed_chart
    lower = transcript.lower()
    if any(w in lower for w in ("кругов", "pie", "доля")):
        return "pie"
    if any(w in lower for w in ("по месяц", "динамик", "тренд", "line", "линейн")):
        return "line"
    return default


def _normalize_intent(
    parsed: dict[str, Any],
    transcript: str,
    default_chart: str,
    default_email: str | None,
    default_format: str = "pdf",
) -> dict[str, Any]:
    email = _normalize_email_value(parsed.get("target_email"))
    if not email:
        email = _extract_email_regex(transcript) or default_email
    else:
        email = _normalize_email_value(email)

    chart = _infer_chart_type(transcript, parsed.get("chart_type"), default_chart)
    output_format = _infer_output_format(transcript, parsed.get("output_format")) or default_format

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
        "output_format": output_format,
        "missing_info": missing,
        "raw_transcript": transcript,
    }


def _fallback_intent(
    text: str,
    default_chart: str,
    default_email: str | None,
    default_format: str = "pdf",
) -> dict[str, Any]:
    url_match = re.search(r"https?://\S+", text)
    source_type = "sheets_url" if url_match else None
    source_value = url_match.group(0).rstrip(".,)") if url_match else None

    missing = []
    if not source_type:
        missing.append("source_type")

    return {
        "source_type": source_type,
        "source_value": source_value,
        "chart_type": _infer_chart_type(text, None, default_chart),
        "metrics": [],
        "group_by": None,
        "target_email": _extract_email_regex(text) or default_email,
        "output_format": _infer_output_format(text, None) or default_format,
        "missing_info": missing,
        "raw_transcript": text,
    }


def merge_clarification_answer(partial_intent: dict[str, Any], answer: str) -> str:
    """Combine original transcript with user's clarification for re-parsing."""
    original = partial_intent.get("raw_transcript") or ""
    return f"{original}\n\nClarification: {answer}".strip()
