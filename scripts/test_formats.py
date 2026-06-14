#!/usr/bin/env python3
"""Benchmark all output formats with the same sample analysis data."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PDF_DIR", str(ROOT / "storage" / "pdfs"))
os.environ.setdefault("FORMATTED_DIR", str(ROOT / "storage" / "formatted"))
os.environ.setdefault("DATABASE_URL", "sqlite:///./app/data/users.db")


def _sample_analysis() -> tuple[dict, list[str]]:
    """Build minimal analysis_data + chart paths from sample CSV."""
    import pandas as pd

    from app.agents.analyst import run_analyst
    from app.agents.parser import run_parser
    from app.agents.visualizer import run_visualizer

    sample = ROOT / "app" / "samples" / "sample_sales.csv"
    if not sample.is_file():
        raise FileNotFoundError(f"Sample CSV not found: {sample}")

    task_id = f"test-formats-{int(time.time())}"
    parsed = run_parser(task_id=task_id, email=None, file_path=str(sample))
    analyzed = run_analyst(parsed)
    visualized = run_visualizer(analyzed)
    charts = visualized.get("chart_paths") or []
    return visualized, charts


def main() -> None:
    from app.agents.formatter import format_report
    from app.config.output_formats import ALLOWED_OUTPUT_FORMATS

    print("Loading sample data...")
    analysis_data, charts = _sample_analysis()
    prefs = {"default_output_format": "pdf", "preferred_chart_type": "bar"}

    formats = sorted(ALLOWED_OUTPUT_FORMATS)
    results: list[dict] = []

    for fmt in formats:
        if fmt in ("notion", "google_slides"):
            token = os.getenv("NOTION_INTEGRATION_TOKEN") if fmt == "notion" else os.getenv("GOOGLE_SLIDES_TEMPLATE_ID")
            if not token:
                print(f"  SKIP {fmt} (credentials not configured)")
                continue

        print(f"Testing format: {fmt}")
        started = time.perf_counter()
        status = "ok"
        size_bytes = 0
        detail = ""

        try:
            result = format_report(analysis_data, charts, fmt, prefs)
            elapsed = time.perf_counter() - started
            if result.file_path and Path(result.file_path).is_file():
                size_bytes = Path(result.file_path).stat().st_size
                detail = result.file_path
            elif result.external_url:
                detail = result.external_url
            else:
                status = "empty"
        except Exception as exc:
            elapsed = time.perf_counter() - started
            status = f"error: {exc}"
            print(f"    FAILED: {exc}")

        row = {
            "format": fmt,
            "status": status,
            "duration_sec": round(elapsed, 3),
            "size_bytes": size_bytes,
            "detail": detail,
        }
        results.append(row)
        print(f"    {json.dumps(row, ensure_ascii=False)}")

    print("\n=== Summary ===")
    for row in results:
        size_kb = row["size_bytes"] / 1024 if row["size_bytes"] else 0
        print(
            f"{row['format']:15} {row['duration_sec']:6.3f}s  "
            f"{size_kb:8.1f} KB  {row['status']}"
        )


if __name__ == "__main__":
    main()
