"""Shared key metrics for preview UI and PDF reports."""

from __future__ import annotations

from typing import Any


def build_key_metrics(analyzed: dict[str, Any]) -> dict[str, Any]:
    """Build human-readable summary metrics from analyst output."""
    numeric_summary: dict[str, dict[str, float | int]] = analyzed.get("numeric_summary") or {}
    categorical_summary: dict[str, list[dict[str, Any]]] = analyzed.get("categorical_summary") or {}

    numeric_cols = list(numeric_summary.keys())
    cat_cols = list(categorical_summary.keys())

    metrics: dict[str, Any] = {
        "row_count": analyzed.get("row_count"),
        "column_count": analyzed.get("column_count"),
    }

    if numeric_cols:
        first = numeric_cols[0]
        metrics[f"sum ({first})"] = numeric_summary[first].get("sum")
        if len(numeric_cols) > 1:
            second = numeric_cols[1]
            metrics[f"mean ({second})"] = numeric_summary[second].get("mean")
        else:
            metrics[f"mean ({first})"] = numeric_summary[first].get("mean")

    for col in cat_cols:
        items = categorical_summary.get(col) or []
        if items:
            metrics[f"top ({col})"] = items[0].get("value")
            break

    return {k: v for k, v in metrics.items() if v is not None and v != ""}
