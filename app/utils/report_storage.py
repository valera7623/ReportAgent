"""Delete on-disk artifacts for a report task."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.utils.paths import FORMATTED_DIR, PDF_BASE_DIR


def delete_task_storage(task_id: str) -> None:
    """Remove PDF/chart and formatted output directories for a task."""
    for base in (PDF_BASE_DIR, FORMATTED_DIR):
        task_dir = base / task_id
        if task_dir.is_dir():
            shutil.rmtree(task_dir, ignore_errors=True)
