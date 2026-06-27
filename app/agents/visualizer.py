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
from app.self_healing.healing_decorator import with_self_healing
from app.utils.fonts import configure_matplotlib_fonts
from app.utils.logger import get_logger
from app.utils.metrics import track_agent_metrics

logger = get_logger("agent_visualizer", "log_visualizer.log")

PDF_BASE_DIR = Path(os.getenv("PDF_DIR", "/app/storage/pdfs"))

CHART_COLORS_LIGHT = {
    "primary": "#4C72B0",
    "secondary": "#55A868",
    "accent": "#C44E52",
    "bg": "white",
    "text": "black",
}

CHART_COLORS_DARK = {
    "primary": "#6BAED6",
    "secondary": "#74C476",
    "accent": "#FC9272",
    "bg": "#1a1a2e",
    "text": "#e8e8e8",
}


def _chart_palette(preferences: dict[str, Any]) -> dict[str, str]:
    if preferences.get("theme") == "dark":
        return CHART_COLORS_DARK
    return CHART_COLORS_LIGHT


def _chart_dir(task_id: str) -> Path:
    path = PDF_BASE_DIR / task_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _apply_chart_style(palette: dict[str, str]) -> None:
    configure_matplotlib_fonts()
    plt.rcParams.update(
        {
            "figure.facecolor": palette["bg"],
            "axes.facecolor": palette["bg"],
            "axes.edgecolor": palette["text"],
            "axes.labelcolor": palette["text"],
            "xtick.color": palette["text"],
            "ytick.color": palette["text"],
            "text.color": palette["text"],
        }
    )


def _save_bar_chart(
    df: pd.DataFrame,
    col: str,
    out_path: Path,
    title: str,
    palette: dict[str, str],
) -> bool:
    series = pd.to_numeric(df[col], errors="coerce").dropna()
    if series.empty:
        return False

    _apply_chart_style(palette)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bins = min(20, max(5, len(series.unique())))
    ax.hist(series, bins=bins, color=palette["primary"], edgecolor=palette["bg"])
    ax.set_title(title)
    ax.set_xlabel(col)
    ax.set_ylabel("Frequency")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, facecolor=palette["bg"])
    plt.close(fig)
    return True


def _save_top_bar(
    df: pd.DataFrame,
    col: str,
    out_path: Path,
    title: str,
    palette: dict[str, str],
) -> bool:
    counts = df[col].astype(str).value_counts().head(10)
    if counts.empty:
        return False

    _apply_chart_style(palette)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    counts.plot(kind="bar", ax=ax, color=palette["secondary"], edgecolor=palette["bg"])
    ax.set_title(title)
    ax.set_xlabel(col)
    ax.set_ylabel("Count")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, facecolor=palette["bg"])
    plt.close(fig)
    return True


def _save_pie_chart(
    df: pd.DataFrame,
    col: str,
    out_path: Path,
    title: str,
    palette: dict[str, str],
) -> bool:
    counts = df[col].astype(str).value_counts().head(10)
    if counts.empty or len(counts) < 2:
        return False

    _apply_chart_style(palette)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors_list = [palette["primary"], palette["secondary"], palette["accent"]] * 4
    ax.pie(
        counts.values,
        labels=counts.index,
        autopct="%1.1f%%",
        colors=colors_list[: len(counts)],
        textprops={"color": palette["text"]},
    )
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, facecolor=palette["bg"])
    plt.close(fig)
    return True


def _save_line_trend(
    df: pd.DataFrame,
    col: str,
    out_path: Path,
    title: str,
    palette: dict[str, str],
) -> bool:
    series = pd.to_numeric(df[col], errors="coerce")
    if series.dropna().empty:
        return False

    _apply_chart_style(palette)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(
        range(len(series)),
        series.values,
        marker="o",
        markersize=3,
        color=palette["accent"],
    )
    ax.set_title(title)
    ax.set_xlabel("Row index")
    ax.set_ylabel(col)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, facecolor=palette["bg"])
    plt.close(fig)
    return True


def _save_xy_bar(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    out_path: Path,
    title: str,
    palette: dict[str, str],
) -> bool:
    if x_col not in df.columns or y_col not in df.columns:
        return False
    grouped = df.groupby(df[x_col].astype(str), dropna=False)[y_col].apply(
        lambda s: pd.to_numeric(s, errors="coerce").sum()
    )
    if grouped.empty:
        return False
    top = grouped.sort_values(ascending=False).head(12)
    _apply_chart_style(palette)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    top.plot(kind="bar", ax=ax, color=palette["primary"], edgecolor=palette["bg"])
    ax.set_title(title)
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, facecolor=palette["bg"])
    plt.close(fig)
    return True


def _save_scatter(
    df: pd.DataFrame,
    x_col: str,
    y_col: str,
    out_path: Path,
    title: str,
    palette: dict[str, str],
) -> bool:
    if x_col not in df.columns or y_col not in df.columns:
        return False
    x = pd.to_numeric(df[x_col], errors="coerce")
    y = pd.to_numeric(df[y_col], errors="coerce")
    mask = x.notna() & y.notna()
    if mask.sum() < 2:
        return False
    _apply_chart_style(palette)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.scatter(x[mask], y[mask], color=palette["secondary"], alpha=0.75)
    ax.set_title(title)
    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, facecolor=palette["bg"])
    plt.close(fig)
    return True


def _create_chart_from_suggestion(
    df: pd.DataFrame,
    suggestion: dict[str, Any],
    out_path: Path,
    palette: dict[str, str],
) -> bool:
    chart_type = str(suggestion.get("type", "bar")).lower()
    x_col = suggestion.get("x")
    y_col = suggestion.get("y")
    title = suggestion.get("title") or "Chart"
    if not x_col or x_col not in df.columns:
        return False

    if chart_type == "pie" and y_col and y_col in df.columns:
        grouped = (
            df.groupby(df[x_col].astype(str), dropna=False)[y_col]
            .apply(lambda s: pd.to_numeric(s, errors="coerce").sum())
            .sort_values(ascending=False)
            .head(10)
        )
        if len(grouped) < 2:
            return False
        _apply_chart_style(palette)
        fig, ax = plt.subplots(figsize=(8, 4.5))
        colors_list = [palette["primary"], palette["secondary"], palette["accent"]] * 4
        ax.pie(
            grouped.values,
            labels=grouped.index,
            autopct="%1.1f%%",
            colors=colors_list[: len(grouped)],
            textprops={"color": palette["text"]},
        )
        ax.set_title(title)
        fig.tight_layout()
        fig.savefig(out_path, dpi=120, facecolor=palette["bg"])
        plt.close(fig)
        return True

    if chart_type == "line" and y_col and y_col in df.columns:
        tmp = df[[x_col, y_col]].copy()
        tmp[y_col] = pd.to_numeric(tmp[y_col], errors="coerce")
        tmp = tmp.dropna(subset=[y_col])
        if tmp.empty:
            return False
        _apply_chart_style(palette)
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.plot(range(len(tmp)), tmp[y_col].values, marker="o", color=palette["accent"])
        ax.set_title(title)
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        fig.tight_layout()
        fig.savefig(out_path, dpi=120, facecolor=palette["bg"])
        plt.close(fig)
        return True

    if chart_type == "scatter" and y_col:
        return _save_scatter(df, x_col, y_col, out_path, title, palette)

    if chart_type in ("bar", "area", "heatmap") and y_col:
        return _save_xy_bar(df, x_col, y_col, out_path, title, palette)

    if chart_type == "pie":
        return _save_pie_chart(df, x_col, out_path, title, palette)

    if pd.api.types.is_numeric_dtype(df[x_col]):
        return _save_bar_chart(df, x_col, out_path, title, palette)
    return _save_top_bar(df, x_col, out_path, title, palette)


def _charts_from_ai_suggestions(
    df: pd.DataFrame,
    suggestions: dict[str, Any],
    chart_dir: Path,
    palette: dict[str, str],
    *,
    max_charts: int = 3,
) -> list[str]:
    paths: list[str] = []
    for idx, item in enumerate(suggestions.get("suggested_charts") or []):
        if len(paths) >= max_charts:
            break
        if not isinstance(item, dict):
            continue
        out = chart_dir / f"chart_ai_{idx}.png"
        if _create_chart_from_suggestion(df, item, out, palette):
            paths.append(str(out))
    return paths


@with_self_healing("visualizer")
@track_agent_metrics("visualizer")
def run_visualizer(analyzed: dict[str, Any], preferences: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create up to 3 PNG charts and return paths."""
    try:
        prefs = preferences or analyzed.get("preferences") or {}
        palette = _chart_palette(prefs)
        preferred_chart = prefs.get("preferred_chart_type", "bar")
        chart_hints = analyzed.get("chart_hints") or {}
        pie_columns: list[str] = chart_hints.get("pie_columns") or []

        task_id = analyzed["task_id"]
        logger.info("Visualizer started for task %s (theme=%s)", task_id, prefs.get("theme"))

        df = pd.DataFrame(analyzed["data"])
        chart_dir = _chart_dir(task_id)
        chart_paths: list[str] = []

        ai_suggestions = analyzed.get("ai_suggestions") or {}
        if ai_suggestions.get("suggested_charts"):
            chart_paths = _charts_from_ai_suggestions(df, ai_suggestions, chart_dir, palette)

        numeric_cols: list[str] = analyzed.get("numeric_columns") or []
        text_cols: list[str] = analyzed.get("text_columns") or []

        if not chart_paths:
            if preferred_chart == "line" and numeric_cols:
                path = chart_dir / "chart_numeric_trend.png"
                if _save_line_trend(df, numeric_cols[0], path, f"Trend: {numeric_cols[0]}", palette):
                    chart_paths.append(str(path))
            elif numeric_cols:
                path = chart_dir / "chart_numeric_hist.png"
                if _save_bar_chart(df, numeric_cols[0], path, f"Distribution: {numeric_cols[0]}", palette):
                    chart_paths.append(str(path))

            if len(numeric_cols) > 1 and len(chart_paths) < 2:
                path = chart_dir / "chart_numeric_trend.png"
                if _save_line_trend(df, numeric_cols[1], path, f"Trend: {numeric_cols[1]}", palette):
                    chart_paths.append(str(path))
            elif preferred_chart != "line" and numeric_cols and len(chart_paths) < 2:
                path = chart_dir / "chart_numeric_trend.png"
                if _save_line_trend(df, numeric_cols[0], path, f"Trend: {numeric_cols[0]}", palette):
                    chart_paths.append(str(path))

            if text_cols and len(chart_paths) < 3:
                cat_col = pie_columns[0] if pie_columns else text_cols[0]
                if preferred_chart == "pie" and cat_col in (pie_columns or text_cols):
                    path = chart_dir / "chart_categorical_pie.png"
                    saved = _save_pie_chart(df, cat_col, path, f"Distribution: {cat_col}", palette)
                else:
                    path = chart_dir / "chart_categorical_top.png"
                    saved = _save_top_bar(df, cat_col, path, f"Top values: {cat_col}", palette)
                if saved:
                    chart_paths.append(str(path))

        if not chart_paths:
            raise AgentError(
                "Could not generate any charts from the available data.",
                agent="visualizer",
            )

        company_logo_url = prefs.get("company_logo_url")
        result = {
            **analyzed,
            "chart_paths": chart_paths,
            "preferences": prefs,
            "company_logo_url": company_logo_url,
        }
        logger.info("Visualizer finished: %d chart(s) saved", len(chart_paths))
        return result

    except AgentError:
        raise
    except Exception as exc:
        logger.exception("Unexpected visualizer error")
        raise AgentError(f"Unexpected error during visualization: {exc}", agent="visualizer") from exc
