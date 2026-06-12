"""Save and validate uploaded voice files."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.voice.config import allowed_audio_extensions, max_audio_size_bytes
from app.utils.logger import get_logger

logger = get_logger("voice_storage", "log_voice.log")

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/storage/uploads"))


def save_voice_upload(content: bytes, filename: str) -> Path:
    """Validate and persist audio to storage/uploads/voice_{uuid}.{ext}."""
    if not content:
        raise ValueError("Uploaded audio file is empty.")

    size_limit = max_audio_size_bytes()
    if len(content) > size_limit:
        raise ValueError(
            f"Audio file exceeds maximum size of {size_limit // (1024 * 1024)} MB."
        )

    ext = Path(filename or "audio.wav").suffix.lower().lstrip(".")
    if not ext:
        ext = "wav"
    if ext not in allowed_audio_extensions():
        allowed = ", ".join(sorted(allowed_audio_extensions()))
        raise ValueError(f"Unsupported audio format '.{ext}'. Allowed: {allowed}")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOAD_DIR / f"voice_{uuid.uuid4().hex}.{ext}"
    dest.write_bytes(content)
    logger.info("Saved voice upload %s (%d bytes)", dest.name, len(content))
    return dest


def delete_voice_file(path: str | Path | None) -> None:
    if not path:
        return
    try:
        p = Path(path)
        if p.is_file():
            p.unlink()
            logger.info("Deleted voice file %s", p.name)
    except OSError as exc:
        logger.warning("Could not delete voice file %s: %s", path, exc)
