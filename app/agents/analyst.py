"""Agent 2: compute basic statistics on parsed data."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.models.schemas import AgentError
from app.self_healing.fix_executor import get_active_fix_context
from app.self_healing.healing_decorator import with_self_healing
from app.utils.logger import get_logger
from app.utils.metrics import track_agent_metrics

logger = get_logger("agent_analyst", "log_analyst.log")


def _top_values(series: pd.Series, n: int = 3) -> list[dict[str, Any]]:
    counts = series.astype(str).value_counts().head(n)
    total = len(series.dropna())
    items = []
    for value, count in counts.items():
        pct = round((count / total) * 100, 2) if total else 0.0
        items.append({"value": str(value), "count": int(count), "percent": pct})
    return items


@with_self_healing("analyst")
@track_agent_metrics("analyst")
def run_analyst(parsed: dict[str, Any], preferences: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compute sums, averages, top values, and percentages."""
    try:
        prefs = preferences or {}
        preferred_chart = prefs.get("preferred_chart_type", "bar")
        task_id = parsed.get("task_id", "unknown")
        logger.info("Analyst started for task %s (chart=%s)", task_id, preferred_chart)

        df = pd.DataFrame(parsed["data"])
        if df.empty:
            raise AgentError("No data available for analysis.", agent="analyst")

        numeric_cols: list[str] = parsed.get("numeric_columns") or []
        text_cols: list[str] = parsed.get("text_columns") or []

        fix_ctx = get_active_fix_context()
        column_remap = fix_ctx.get("_column_remap") or {}
        if column_remap:
            numeric_cols = [column_remap.get(c, c) for c in numeric_cols]
            text_cols = [column_remap.get(c, c) for c in text_cols]
            logger.info("Applied fuzzy column remap: %s", column_remap)

        numeric_summary: dict[str, dict[str, float | int]] = {}
        for col in numeric_cols:
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            if series.empty:
                continue
            numeric_summary[col] = {
                "sum": round(float(series.sum()), 2),
                "mean": round(float(series.mean()), 2),
                "min": round(float(series.min()), 2),
                "max": round(float(series.max()), 2),
                "count": int(series.count()),
            }

        cat_top_n = 10 if preferred_chart == "pie" else 3
        categorical_summary: dict[str, list[dict[str, Any]]] = {}
        pie_candidates: list[str] = []

        for col in text_cols:
            series = df[col].dropna()
            if series.empty:
                continue
            unique_count = series.astype(str).nunique()
            items = _top_values(series, n=cat_top_n)
            categorical_summary[col] = items
            if preferred_chart == "pie" and 2 <= unique_count <= 12:
                pie_candidates.append(col)

        if not numeric_summary and not categorical_summary:
            raise AgentError(
                "No analyzable columns found. Add numeric or categorical data.",
                agent="analyst",
            )

        result = {
            "task_id": task_id,
            "email": parsed["email"],
            "source": parsed.get("source", "unknown"),
            "row_count": parsed.get("row_count", len(df)),
            "column_count": parsed.get("column_count", len(df.columns)),
            "columns": parsed.get("columns", list(df.columns)),
            "numeric_columns": numeric_cols,
            "text_columns": text_cols,
            "numeric_summary": numeric_summary,
            "categorical_summary": categorical_summary,
            "data": parsed["data"],
            "preferences": prefs,
            "chart_hints": {
                "preferred_chart_type": preferred_chart,
                "pie_columns": pie_candidates[:1] if pie_candidates else [],
            },
        }

        logger.info(
            "Analyst finished: %d numeric cols, %d categorical cols, pie_cols=%s",
            len(numeric_summary),
            len(categorical_summary),
            pie_candidates,
        )
        return result

    except AgentError:
        raise
    except Exception as exc:
        logger.exception("Unexpected analyst error")
        raise AgentError(f"Unexpected error during analysis: {exc}", agent="analyst") from exc
