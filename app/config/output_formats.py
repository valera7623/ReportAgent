"""Output format configuration and validation."""

from __future__ import annotations

import os

DEFAULT_OUTPUT_FORMAT = os.getenv("DEFAULT_OUTPUT_FORMAT", "pdf").strip().lower()

ALLOWED_OUTPUT_FORMATS: frozenset[str] = frozenset(
    fmt.strip().lower()
    for fmt in os.getenv(
        "ALLOWED_OUTPUT_FORMATS",
        "pdf,excel,pptx,notion,google_slides",
    ).split(",")
    if fmt.strip()
)

FORMAT_EXTENSIONS: dict[str, str] = {
    "pdf": "pdf",
    "excel": "xlsx",
    "pptx": "pptx",
    "notion": "",
    "google_slides": "",
}

FORMAT_CONTENT_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "notion": "text/html",
    "google_slides": "text/html",
}

EXTERNAL_FORMATS = frozenset({"notion", "google_slides"})


def normalize_output_format(value: str | None, fallback: str | None = None) -> str:
    """Return validated output format or raise ValueError."""
    default = fallback or DEFAULT_OUTPUT_FORMAT
    fmt = (value or default).strip().lower()
    if fmt not in ALLOWED_OUTPUT_FORMATS:
        allowed = ", ".join(sorted(ALLOWED_OUTPUT_FORMATS))
        raise ValueError(
            f"Unsupported output_format '{fmt}'. Allowed values: {allowed}"
        )
    return fmt


def resolve_output_format(
    request_format: str | None,
    user_preferences: dict | None = None,
) -> str:
    """Pick format: request > user preference > env default."""
    prefs = user_preferences or {}
    pref_format = prefs.get("default_output_format")
    fallback = pref_format or DEFAULT_OUTPUT_FORMAT
    return normalize_output_format(request_format, fallback=fallback)
