"""Generate report previews using existing agents (no DB / no email)."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.agents.analyst import run_analyst
from app.agents.parser import run_parser
from app.agents.visualizer import (
    _chart_palette,
    _save_bar_chart,
    _save_line_trend,
    _save_pie_chart,
    _save_top_bar,
    run_visualizer,
)
from app.preview.cache import preview_storage_dir, store_chart_png
from app.preview.summary import build_key_metrics
from app.utils.logger import get_logger

logger = get_logger("preview_generator", "log_api.log")

SAMPLE_ROW_LIMIT = 50
SUGGESTED_CHART_TYPES = ["bar", "line", "pie"]
ASYNC_THRESHOLD_MB = int(os.getenv("PREVIEW_ASYNC_THRESHOLD_MB", "10"))


class PreviewGenerator:
    """Build preview payloads from uploaded files or Google Sheets."""

    def generate_preview(
        self,
        *,
        user_id: str,
        file_path: str | None = None,
        sheets_url: str | None = None,
        preferences: dict[str, Any] | None = None,
        preview_id: str | None = None,
    ) -> dict[str, Any]:
        preview_id = preview_id or str(uuid.uuid4())
        prefs = preferences or {}

        parsed = self._parse_data(
            preview_id=preview_id,
            file_path=file_path,
            sheets_url=sheets_url,
        )
        analyzed = run_analyst(parsed, preferences=prefs)
        visualized = run_visualizer(analyzed, preferences=prefs)

        df = pd.DataFrame(analyzed["data"])
        summary = build_key_metrics(analyzed)
        columns = self._detect_column_types(df)
        charts_meta = self._build_charts_from_visualized(preview_id, visualized, prefs)
        chart_specs = visualized.get("_preview_chart_specs") or self._chart_specs_from_meta(charts_meta)

        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        data = {
            "headers": list(df.columns),
            "rows": self._sample_rows(df, limit=SAMPLE_ROW_LIMIT),
            "total_rows": int(analyzed.get("row_count", len(df))),
            "summary": summary,
            "charts": charts_meta,
            "suggested_chart_types": self._suggest_chart_types(analyzed),
            "columns": columns,
        }

        cache_payload = {
            "expires_at": expires_at,
            "file_path": file_path,
            "sheets_url": sheets_url,
            "preferences": prefs,
            "chart_specs": chart_specs,
            "analyzed": {
                "numeric_columns": analyzed.get("numeric_columns", []),
                "text_columns": analyzed.get("text_columns", []),
                "numeric_summary": analyzed.get("numeric_summary", {}),
                "categorical_summary": analyzed.get("categorical_summary", {}),
                "chart_hints": analyzed.get("chart_hints", {}),
            },
            "data": data,
        }

        return {
            "preview_id": preview_id,
            "data": data,
            "expires_at": expires_at,
            "_cache_payload": cache_payload,
        }

    def _parse_data(
        self,
        *,
        preview_id: str,
        file_path: str | None,
        sheets_url: str | None,
    ) -> dict[str, Any]:
        return run_parser(
            task_id=preview_id,
            email=None,
            sheets_url=sheets_url,
            file_path=file_path,
        )

    def _detect_column_types(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        columns: list[dict[str, Any]] = []
        for col in df.columns:
            series = df[col]
            if pd.api.types.is_numeric_dtype(series):
                col_type = "numeric"
            elif pd.api.types.is_datetime64_any_dtype(series):
                col_type = "date"
            else:
                sample_val = series.dropna().iloc[0] if not series.dropna().empty else ""
                try:
                    pd.to_datetime(sample_val)
                    col_type = "date"
                except (ValueError, TypeError):
                    col_type = "text"

            sample = series.dropna().iloc[0] if not series.dropna().empty else ""
            if col_type == "date":
                try:
                    sample = pd.to_datetime(sample).strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    sample = str(sample)
            else:
                sample = str(sample)[:80]

            columns.append({"name": str(col), "type": col_type, "sample": sample})
        return columns

    def _sample_rows(self, df: pd.DataFrame, limit: int = 50) -> list[list[Any]]:
        sample = df.head(limit)
        rows: list[list[Any]] = []
        for _, row in sample.iterrows():
            cells = []
            for val in row:
                if pd.isna(val):
                    cells.append(None)
                elif hasattr(val, "isoformat"):
                    cells.append(val.isoformat())
                else:
                    cells.append(val)
            rows.append(cells)
        return rows

    def _suggest_chart_types(self, analyzed: dict[str, Any]) -> list[str]:
        preferred = (analyzed.get("chart_hints") or {}).get("preferred_chart_type", "bar")
        suggestions = [preferred]
        for t in SUGGESTED_CHART_TYPES:
            if t not in suggestions:
                suggestions.append(t)
        return suggestions[:3]

    def _build_charts_from_visualized(
        self,
        preview_id: str,
        visualized: dict[str, Any],
        prefs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        chart_paths: list[str] = visualized.get("chart_paths") or []
        specs: list[dict[str, Any]] = []
        df = pd.DataFrame(visualized["data"])
        palette = _chart_palette(prefs)
        preferred = prefs.get("preferred_chart_type", "bar")
        numeric_cols = visualized.get("numeric_columns") or []
        text_cols = visualized.get("text_columns") or []

        for idx, path_str in enumerate(chart_paths):
            path = Path(path_str)
            if path.is_file():
                store_chart_png(preview_id, idx, path.read_bytes())

            chart_type = preferred
            title = path.stem.replace("_", " ").title()
            column = numeric_cols[0] if numeric_cols else (text_cols[0] if text_cols else "")

            if "pie" in path.name:
                chart_type = "pie"
                column = text_cols[0] if text_cols else column
                title = f"Distribution: {column}"
            elif "trend" in path.name or "line" in path.name:
                chart_type = "line"
                title = f"Trend: {column}"
            elif "hist" in path.name:
                chart_type = "bar"
                title = f"Distribution: {column}"
            elif "categorical" in path.name or "top" in path.name:
                chart_type = "bar"
                column = text_cols[0] if text_cols else column
                title = f"Top values: {column}"

            specs.append(
                {
                    "type": chart_type,
                    "title": title,
                    "column": column,
                    "image_url": f"/api/preview/chart/{preview_id}/{idx}",
                }
            )

        visualized["_preview_chart_specs"] = [
            {**s, "index": i} for i, s in enumerate(specs)
        ]
        return specs

    def _chart_specs_from_meta(self, charts_meta: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{**c, "index": i} for i, c in enumerate(charts_meta)]

    def regenerate_chart(
        self,
        *,
        preview_id: str,
        chart_index: int,
        chart_type: str,
        preview_record: dict[str, Any],
    ) -> dict[str, Any]:
        file_path = preview_record.get("file_path")
        sheets_url = preview_record.get("sheets_url")
        prefs = preview_record.get("preferences") or {}
        analyzed_meta = preview_record.get("analyzed") or {}

        parsed = self._parse_data(
            preview_id=preview_id,
            file_path=file_path,
            sheets_url=sheets_url,
        )
        df = pd.DataFrame(parsed["data"])
        palette = _chart_palette(prefs)

        numeric_cols = analyzed_meta.get("numeric_columns") or parsed.get("numeric_columns") or []
        text_cols = analyzed_meta.get("text_columns") or parsed.get("text_columns") or []
        chart_hints = analyzed_meta.get("chart_hints") or {}
        pie_columns = chart_hints.get("pie_columns") or []

        out_dir = preview_storage_dir(preview_id)
        out_path = out_dir / f"chart_{chart_index}.png"
        chart_type = chart_type.lower().strip()

        saved = False
        title = "Chart"
        column = ""

        if chart_type == "pie" and text_cols:
            column = pie_columns[0] if pie_columns else text_cols[0]
            title = f"Distribution: {column}"
            saved = _save_pie_chart(df, column, out_path, title, palette)
        elif chart_type == "line" and numeric_cols:
            column = numeric_cols[min(chart_index, len(numeric_cols) - 1)]
            title = f"Trend: {column}"
            saved = _save_line_trend(df, column, out_path, title, palette)
        elif numeric_cols:
            column = numeric_cols[min(chart_index, len(numeric_cols) - 1)]
            title = f"Distribution: {column}"
            saved = _save_bar_chart(df, column, out_path, title, palette)
        elif text_cols:
            column = text_cols[0]
            title = f"Top values: {column}"
            saved = _save_top_bar(df, column, out_path, title, palette)

        if not saved or not out_path.is_file():
            raise ValueError("Could not regenerate chart with the requested type")

        store_chart_png(preview_id, chart_index, out_path.read_bytes())

        specs: list[dict[str, Any]] = preview_record.get("chart_specs") or []
        while len(specs) <= chart_index:
            specs.append({"type": "bar", "title": "Chart", "column": "", "index": len(specs)})
        specs[chart_index] = {
            "type": chart_type,
            "title": title,
            "column": column,
            "index": chart_index,
            "image_url": f"/api/preview/chart/{preview_id}/{chart_index}",
        }
        preview_record["chart_specs"] = specs
        if preview_record.get("data") and preview_record["data"].get("charts"):
            preview_record["data"]["charts"][chart_index] = specs[chart_index]

        return {
            "image_url": specs[chart_index]["image_url"],
            "chart": specs[chart_index],
        }


def file_size_mb(file_path: str | None) -> float:
    if not file_path:
        return 0.0
    try:
        return Path(file_path).stat().st_size / (1024 * 1024)
    except OSError:
        return 0.0
