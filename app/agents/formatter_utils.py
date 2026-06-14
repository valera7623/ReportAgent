"""Shared utilities for multi-format report generation."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from app.utils.logger import get_logger

logger = get_logger("agent_formatter", "log_formatter.log")

_MAX_TEXT_LEN = 2000
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(value: Any, max_len: int = _MAX_TEXT_LEN) -> str:
    """Strip control characters and truncate for safe export."""
    text = str(value) if value is not None else ""
    text = _CONTROL_CHARS.sub("", text)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def prepare_kpi_table(analysis_data: dict[str, Any]) -> list[tuple[str, str]]:
    """Build key metrics rows for slides/spreadsheets."""
    rows: list[tuple[str, str]] = [
        ("Rows", str(analysis_data.get("row_count", "—"))),
        ("Columns", str(analysis_data.get("column_count", "—"))),
        ("Source", sanitize_text(analysis_data.get("source", "N/A"), 120)),
    ]

    numeric_summary: dict[str, dict[str, float | int]] = analysis_data.get("numeric_summary") or {}
    for col, stats in list(numeric_summary.items())[:5]:
        rows.append((f"Sum ({col})", str(stats.get("sum", "—"))))
        rows.append((f"Avg ({col})", str(stats.get("mean", "—"))))

    categorical_summary: dict[str, list[dict[str, Any]]] = (
        analysis_data.get("categorical_summary") or {}
    )
    for col, items in list(categorical_summary.items())[:2]:
        if items:
            top = items[0]
            rows.append(
                (
                    f"Top {col}",
                    f"{sanitize_text(top.get('value'), 60)} ({top.get('count', 0)})",
                )
            )

    return rows


def create_chart_image(chart_path: str | Path, max_width: int = 800) -> BytesIO | None:
    """Load chart PNG and return resized BytesIO for embedding."""
    path = Path(chart_path)
    if not path.is_file():
        logger.warning("Chart file not found: %s", path)
        return None

    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            if img.width > max_width:
                ratio = max_width / img.width
                new_size = (max_width, int(img.height * ratio))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)
            return buffer
    except Exception as exc:
        logger.warning("Failed to process chart %s: %s", path, exc)
        return None


def get_data_rows(analysis_data: dict[str, Any], limit: int = 10000) -> list[dict[str, Any]]:
    """Return raw data rows capped at limit."""
    data = analysis_data.get("data") or []
    return data[:limit]


def get_display_columns(analysis_data: dict[str, Any], max_cols: int = 3) -> list[str]:
    """Pick up to max_cols columns for compact tables (Notion, previews)."""
    columns = analysis_data.get("columns") or []
    if columns:
        return list(columns)[:max_cols]
    data = analysis_data.get("data") or []
    if data and isinstance(data[0], dict):
        return list(data[0].keys())[:max_cols]
    return []


def build_summary_rows(analysis_data: dict[str, Any]) -> list[list[str]]:
    """Summary sheet rows: numeric aggregates + top categories."""
    rows: list[list[str]] = [["Metric", "Value"]]

    for label, value in prepare_kpi_table(analysis_data):
        rows.append([label, value])

    numeric_summary = analysis_data.get("numeric_summary") or {}
    if numeric_summary:
        rows.append(["", ""])
        rows.append(["Numeric column", "Sum", "Mean", "Min", "Max", "Count"])
        for col, stats in numeric_summary.items():
            rows.append(
                [
                    col,
                    str(stats.get("sum", "")),
                    str(stats.get("mean", "")),
                    str(stats.get("min", "")),
                    str(stats.get("max", "")),
                    str(stats.get("count", "")),
                ]
            )

    categorical_summary = analysis_data.get("categorical_summary") or {}
    for col, items in categorical_summary.items():
        rows.append(["", ""])
        rows.append([f"Top values — {col}", "Count", "%"])
        for item in items[:3]:
            rows.append(
                [
                    sanitize_text(item.get("value"), 80),
                    str(item.get("count", "")),
                    f"{item.get('percent', 0)}%",
                ]
            )

    return rows
