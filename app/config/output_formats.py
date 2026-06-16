"""Output format configuration and validation."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException

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


def validate_format_credentials(output_format: str) -> None:
    """Raise HTTPException if external format requested without credentials."""
    if output_format == "notion":
        if not os.getenv("NOTION_INTEGRATION_TOKEN", "").strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Notion export requires NOTION_INTEGRATION_TOKEN. "
                    "Configure .env or choose another output_format."
                ),
            )
        if not os.getenv("NOTION_DATABASE_ID", "").strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Notion export requires NOTION_DATABASE_ID. "
                    "Configure .env or choose another output_format."
                ),
            )
    if output_format == "google_slides":
        sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "./secrets/google-sa.json")
        if not Path(sa_path).is_file():
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Google Slides export requires service account JSON at {sa_path}. "
                    "Mount secrets/google-sa.json or choose another output_format."
                ),
            )
        if not os.getenv("GOOGLE_SLIDES_TEMPLATE_ID", "").strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    "Google Slides export requires GOOGLE_SLIDES_TEMPLATE_ID. "
                    "Configure .env or choose another output_format."
                ),
            )
