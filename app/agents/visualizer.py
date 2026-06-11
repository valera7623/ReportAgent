"""Agent 3: generate 2-3 static charts with matplotlib (Agg backend)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd

from app.models.schemas import AgentError
from app.utils.logger import get_logger

logger = get_logger("agent_visualizer", "log_visualizer.log")

PDF_BASE_DIR = Path(os.getenv("PDF_DIR", "/app/storage/pdfs"))


def _chart_dir(task_id: str) -> Path:
    path = PDF_BASE_DIR / task_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_bar_chart(df: pd.DataFrame, col: str, out_path: Path, title: str) -> bool:
    series = pd.to_numeric(df[col], errors="coerce").dropna()
    if series.empty:
        return False

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bins = min(20, max(5, len(series.unique())))
    ax.hist(series, bins=bins, color="#4C72B0", edgecolor="white")
    ax.set_title(title)
    ax.set_xlabel(col)
    ax.set_ylabel("Frequency")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True


def _save_top_bar(df: pd.DataFrame, col: str, out_path: Path, title: str) -> bool:
    counts = df[col].astype(str).value_counts().head(10)
    if counts.empty:
        return False

    fig, ax = plt.subplots(figsize=(8, 4.5))
    counts.plot(kind="bar", ax=ax, color="#55A868", edgecolor="white")
    ax.set_title(title)
    ax.set_xlabel(col)
    ax.set_ylabel("Count")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True


def _save_line_trend(df: pd.DataFrame, col: str, out_path: Path, title: str) -> bool:
    series = pd.to_numeric(df[col], errors="coerce")
    if series.dropna().empty:
        return False

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(range(len(series)), series.values, marker="o", markersize=3, color="#C44E52")
    ax.set_title(title)
    ax.set_xlabel("Row index")
    ax.set_ylabel(col)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True


def run_visualizer(analyzed: dict[str, Any]) -> dict[str, Any]:
    """Create up to 3 PNG charts and return paths."""
    try:
        task_id = analyzed["task_id"]
        logger.info("Visualizer started for task %s", task_id)

        df = pd.DataFrame(analyzed["data"])
        chart_dir = _chart_dir(task_id)
        chart_paths: list[str] = []

        numeric_cols: list[str] = analyzed.get("numeric_columns") or []
        text_cols: list[str] = analyzed.get("text_columns") or []

        if numeric_cols:
            path = chart_dir / "chart_numeric_hist.png"
            if _save_bar_chart(df, numeric_cols[0], path, f"Distribution: {numeric_cols[0]}"):
                chart_paths.append(str(path))

        if len(numeric_cols) > 1:
            path = chart_dir / "chart_numeric_trend.png"
            if _save_line_trend(df, numeric_cols[1], path, f"Trend: {numeric_cols[1]}"):
                chart_paths.append(str(path))
        elif numeric_cols and len(chart_paths) < 2:
            path = chart_dir / "chart_numeric_trend.png"
            if _save_line_trend(df, numeric_cols[0], path, f"Trend: {numeric_cols[0]}"):
                chart_paths.append(str(path))

        if text_cols and len(chart_paths) < 3:
            path = chart_dir / "chart_categorical_top.png"
            if _save_top_bar(df, text_cols[0], path, f"Top values: {text_cols[0]}"):
                chart_paths.append(str(path))

        if not chart_paths:
            raise AgentError(
                "Could not generate any charts from the available data.",
                agent="visualizer",
            )

        result = {**analyzed, "chart_paths": chart_paths}
        logger.info("Visualizer finished: %d chart(s) saved", len(chart_paths))
        return result

    except AgentError:
        raise
    except Exception as exc:
        logger.exception("Unexpected visualizer error")
        raise AgentError(f"Unexpected error during visualization: {exc}", agent="visualizer") from exc
