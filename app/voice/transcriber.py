"""Speech-to-text via OpenAI Whisper API."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.voice.config import WHISPER_MODEL
from app.utils.logger import get_logger

logger = get_logger("voice_transcriber", "log_voice.log")


def _audio_duration_seconds(file_path: Path) -> float | None:
    try:
        from pydub import AudioSegment

        segment = AudioSegment.from_file(str(file_path))
        return len(segment) / 1000.0
    except Exception as exc:
        logger.debug("Could not read audio duration via pydub: %s", exc)
        return None


def transcribe_audio(file_path: str) -> dict[str, Any]:
    """
    Transcribe audio file to text using OpenAI Whisper API.

    Returns dict with keys: text, duration_seconds, confidence.
    On API failure returns empty text and logs the error.
    """
    path = Path(file_path)
    if not path.is_file():
        logger.error("Audio file not found: %s", file_path)
        return {"text": "", "duration_seconds": None, "confidence": None}

    duration = _audio_duration_seconds(path)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.error("OPENAI_API_KEY not configured; transcription skipped")
        return {"text": "", "duration_seconds": duration, "confidence": None}

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = WHISPER_MODEL()

        with path.open("rb") as audio_file:
            if model == "whisper-1":
                response = client.audio.transcriptions.create(
                    model=model,
                    file=audio_file,
                    response_format="verbose_json",
                )
                text = (response.text or "").strip()
                confidence = _extract_confidence(response)
            else:
                response = client.audio.transcriptions.create(
                    model=model,
                    file=audio_file,
                )
                text = (response if isinstance(response, str) else getattr(response, "text", "")).strip()
                confidence = None

        logger.info(
            "Transcribed %s: duration=%.1fs chars=%d confidence=%s",
            path.name,
            duration or 0,
            len(text),
            confidence,
        )
        return {
            "text": text,
            "duration_seconds": duration,
            "confidence": confidence,
        }

    except Exception as exc:
        logger.exception("Whisper API failed for %s: %s", path.name, exc)
        return {"text": "", "duration_seconds": duration, "confidence": None}


def _extract_confidence(response: Any) -> float | None:
    """Best-effort confidence from verbose_json segments."""
    segments = getattr(response, "segments", None)
    if not segments:
        return None
    scores: list[float] = []
    for seg in segments:
        if isinstance(seg, dict):
            if "avg_logprob" in seg:
                scores.append(float(seg["avg_logprob"]))
            elif "no_speech_prob" in seg:
                scores.append(1.0 - float(seg["no_speech_prob"]))
        else:
            if hasattr(seg, "avg_logprob"):
                scores.append(float(seg.avg_logprob))
            elif hasattr(seg, "no_speech_prob"):
                scores.append(1.0 - float(seg.no_speech_prob))
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)
