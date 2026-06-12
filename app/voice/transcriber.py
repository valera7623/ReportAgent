"""Speech-to-text via OpenAI Whisper API."""

from __future__ import annotations

import os
import tempfile
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
        logger.warning("Could not read audio duration via pydub for %s: %s", file_path.name, exc)
        return None


def _normalize_audio_for_whisper(source: Path) -> tuple[Path, Path | None]:
    """
    Convert audio to 16 kHz mono WAV for reliable Whisper transcription.

    Returns (path_to_send, temp_path_to_delete_or_none).
    """
    try:
        from pydub import AudioSegment

        segment = AudioSegment.from_file(str(source))
        if len(segment) < 100:
            raise ValueError(f"Audio too short ({len(segment)} ms)")

        normalized = segment.set_channels(1).set_frame_rate(16000)
        tmp = Path(tempfile.mkstemp(suffix=".wav", prefix="voice_norm_")[1])
        normalized.export(str(tmp), format="wav")
        logger.info(
            "Normalized %s -> %s (duration=%.1fs, channels=1, rate=16000)",
            source.name,
            tmp.name,
            len(normalized) / 1000.0,
        )
        return tmp, tmp
    except Exception as exc:
        logger.warning("Audio normalize failed for %s, using original: %s", source.name, exc)
        return source, None


def transcribe_audio(file_path: str) -> dict[str, Any]:
    """
    Transcribe audio file to text using OpenAI Whisper API.

    Returns dict: text, duration_seconds, confidence, error (if any).
    """
    path = Path(file_path)
    if not path.is_file():
        msg = f"Audio file not found: {file_path}"
        logger.error(msg)
        return {"text": "", "duration_seconds": None, "confidence": None, "error": msg}

    if path.stat().st_size == 0:
        msg = "Audio file is empty (0 bytes)"
        logger.error(msg)
        return {"text": "", "duration_seconds": 0, "confidence": None, "error": msg}

    duration = _audio_duration_seconds(path)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        msg = "OPENAI_API_KEY not configured in container environment"
        logger.error(msg)
        return {"text": "", "duration_seconds": duration, "confidence": None, "error": msg}

    whisper_path, temp_path = _normalize_audio_for_whisper(path)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = WHISPER_MODEL()

        with whisper_path.open("rb") as audio_file:
            if model == "whisper-1":
                response = client.audio.transcriptions.create(
                    model=model,
                    file=audio_file,
                    response_format="verbose_json",
                    language="ru",
                )
                text = (response.text or "").strip()
                confidence = _extract_confidence(response)
            else:
                response = client.audio.transcriptions.create(
                    model=model,
                    file=audio_file,
                    language="ru",
                )
                text = (
                    response if isinstance(response, str) else getattr(response, "text", "")
                ).strip()
                confidence = None

        if not text:
            msg = "Whisper returned empty transcript (silent or unrecognized audio)"
            logger.warning("%s for %s", msg, path.name)
            return {
                "text": "",
                "duration_seconds": duration,
                "confidence": confidence,
                "error": msg,
            }

        logger.info(
            "Transcribed %s: duration=%.1fs chars=%d confidence=%s preview=%r",
            path.name,
            duration or 0,
            len(text),
            confidence,
            text[:80],
        )
        return {
            "text": text,
            "duration_seconds": duration,
            "confidence": confidence,
            "error": None,
        }

    except Exception as exc:
        msg = f"Whisper API error: {exc}"
        logger.exception("Whisper API failed for %s", path.name)
        return {"text": "", "duration_seconds": duration, "confidence": None, "error": msg}

    finally:
        if temp_path and temp_path.is_file():
            try:
                temp_path.unlink()
            except OSError:
                pass


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
