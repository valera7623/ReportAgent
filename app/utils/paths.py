"""Shared storage paths."""

from __future__ import annotations

import os
from pathlib import Path

PDF_BASE_DIR = Path(os.getenv("PDF_DIR", "/app/storage/pdfs"))


def resolve_pdf_path(task_id: str, pdf_path: str | None = None) -> Path:
    """Return PDF path from task result or default location."""
    if pdf_path:
        return Path(pdf_path)
    return PDF_BASE_DIR / task_id / f"report_{task_id}.pdf"
