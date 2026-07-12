"""Voice feature configuration from environment."""

from __future__ import annotations

import os


def voice_enabled() -> bool:
    return os.getenv("VOICE_ENABLED", "true").lower() in ("1", "true", "yes")


def openai_configured() -> bool:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return bool(key)


def voice_available() -> bool:
    return voice_enabled() and openai_configured()


def max_audio_size_bytes() -> int:
    mb = int(os.getenv("MAX_AUDIO_SIZE_MB", "25"))
    return mb * 1024 * 1024


def allowed_audio_extensions() -> frozenset[str]:
    raw = os.getenv("ALLOWED_AUDIO_FORMATS", "mp3,wav,m4a,ogg,webm")
    return frozenset(ext.strip().lower().lstrip(".") for ext in raw.split(",") if ext.strip())


WHISPER_MODEL = lambda: os.getenv("WHISPER_MODEL", "whisper-1")
LLM_MODEL = lambda: os.getenv("LLM_MODEL", "gpt-4o-mini")
