"""Agent 2: compute basic statistics on parsed data."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.models.schemas import AgentError
from app.utils.logger import get_logger

logger = get_logger("agent_analyst", "log_analyst.log")


def _top_values(series: pd.Series, n: int = 3) -> list[dict[str, Any]]:
    counts = series.astype(str).value_counts().head(n)
    total = len(series.dropna())
    items = []
    for value, count in counts.items():
        pct = round((count / total) * 100, 2) if total else 0.0
        items.append({"value": str(value), "count": int(count), "percent": pct})
    return items


def run_analyst(parsed: dict[str, Any]) -> dict[str, Any]:
    """Compute sums, averages, top-3 values, and percentages."""
    try:
        task_id = parsed.get("task_id", "unknown")
        logger.info("Analyst started for task %s", task_id)

        df = pd.DataFrame(parsed["data"])
        if df.empty:
            raise AgentError("No data available for analysis.", agent="analyst")

        numeric_cols: list[str] = parsed.get("numeric_columns") or []
        text_cols: list[str] = parsed.get("text_columns") or []

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

        categorical_summary: dict[str, list[dict[str, Any]]] = {}
        for col in text_cols:
            series = df[col].dropna()
            if series.empty:
                continue
            categorical_summary[col] = _top_values(series, n=3)

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
        }

        logger.info(
            "Analyst finished: %d numeric cols, %d categorical cols",
            len(numeric_summary),
            len(categorical_summary),
        )
        return result

    except AgentError:
        raise
    except Exception as exc:
        logger.exception("Unexpected analyst error")
        raise AgentError(f"Unexpected error during analysis: {exc}", agent="analyst") from exc
