"""Shared storage paths."""

from __future__ import annotations

import os
from pathlib import Path

from app.config.output_formats import EXTERNAL_FORMATS, FORMAT_EXTENSIONS

PDF_BASE_DIR = Path(os.getenv("PDF_DIR", "/app/storage/pdfs"))
FORMATTED_DIR = Path(os.getenv("FORMATTED_DIR", "/app/storage/formatted"))


def resolve_pdf_path(task_id: str, pdf_path: str | None = None) -> Path:
    """Return PDF path from task result or default location."""
    if pdf_path:
        return Path(pdf_path)
    return PDF_BASE_DIR / task_id / f"report_{task_id}.pdf"


def resolve_formatted_path(
    task_id: str,
    output_format: str,
    file_path: str | None = None,
) -> Path | None:
    """Return local formatted file path for a task."""
    if output_format in EXTERNAL_FORMATS:
        return None
    if file_path:
        return Path(file_path)
    ext = FORMAT_EXTENSIONS.get(output_format, output_format)
    return FORMATTED_DIR / task_id / f"report_{task_id}.{ext}"
