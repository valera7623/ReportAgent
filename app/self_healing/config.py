"""Self-healing configuration and runtime guards."""

from __future__ import annotations

import os
from pathlib import Path

from app.utils.logger import get_logger

logger = get_logger("self_healing_config", "log_self_healing.json")

SELF_HEALING_ENABLED = os.getenv("SELF_HEALING_ENABLED", "true").lower() in ("1", "true", "yes")
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
)
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.75"))
MAX_RETRY_ATTEMPTS = int(os.getenv("MAX_RETRY_ATTEMPTS", "2"))
SELF_HEALING_LOG_LEVEL = os.getenv("SELF_HEALING_LOG_LEVEL", "info").lower()
FIX_ATTEMPT_TIMEOUT_SECONDS = int(os.getenv("FIX_ATTEMPT_TIMEOUT_SECONDS", "30"))
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "").strip()
MIN_RAM_BYTES = 1 * 1024 * 1024 * 1024  # 1 GB

# Agents where automatic code fixes are allowed (non-destructive).
SAFE_FIX_AGENTS = frozenset(
    {
        "parser",
        "analyst",
        "visualizer",
        "intent_parser",
        "formatter",
    }
)

# Errors that require human intervention — never auto-fix.
NON_HEALABLE_PATTERNS = (
    "api key",
    "authentication",
    "401",
    "403 forbidden",
    "expired",
    "invalid api key",
    "quota exceeded",
    "insufficient_quota",
)


def _available_ram_bytes() -> int | None:
    """Return available system RAM in bytes, or None if unknown."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb * 1024
    except OSError:
        pass
    return None


def is_self_healing_enabled() -> bool:
    """Return True when self-healing should be active."""
    if not SELF_HEALING_ENABLED:
        return False

    ram = _available_ram_bytes()
    if ram is not None and ram < MIN_RAM_BYTES:
        logger.warning(
            "Self-healing disabled: available RAM %.0f MB < 1 GB",
            ram / (1024 * 1024),
        )
        return False

    return True


def is_healable_error(error_text: str) -> bool:
    """Return False for errors that need manual intervention."""
    lower = error_text.lower()
    return not any(pattern in lower for pattern in NON_HEALABLE_PATTERNS)


def ensure_chroma_dir() -> Path:
    """Create ChromaDB persist directory if missing."""
    path = Path(CHROMA_PERSIST_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path
