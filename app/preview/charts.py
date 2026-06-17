"""Reuse preview chart images in final report generation."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.preview.cache import PREVIEW_DIR
from app.utils.logger import get_logger

logger = get_logger("preview_charts", "log_api.log")

PDF_BASE_DIR = Path(__import__("os").getenv("PDF_DIR", "/app/storage/pdfs"))


def import_preview_charts(preview_id: str, task_id: str) -> list[str]:
    """Copy chart PNGs from preview storage into the report task directory."""
    src_dir = PREVIEW_DIR / preview_id
    if not src_dir.is_dir():
        return []

    dst_dir = PDF_BASE_DIR / task_id
    dst_dir.mkdir(parents=True, exist_ok=True)

    paths: list[str] = []
    for idx, src in enumerate(sorted(src_dir.glob("chart_*.png"))):
        dst = dst_dir / f"chart_{idx}{src.suffix}"
        try:
            shutil.copy2(src, dst)
            paths.append(str(dst))
        except OSError as exc:
            logger.warning("Failed to copy preview chart %s: %s", src, exc)

    if paths:
        logger.info("Imported %d preview chart(s) for task %s", len(paths), task_id)
    return paths
