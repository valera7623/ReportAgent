#!/usr/bin/env python3
"""Test AI Enhancer column detection and suggestions (heuristic + optional OpenAI)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd

from app.services.ai_enhancer import AIEnhancer


def build_sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "month": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
            "sales": [100, 120, 110, 150, 180, 200],
            "profit": [20, 25, 22, 30, 35, 40],
            "product": ["A", "A", "B", "B", "C", "C"],
            "region": ["North", "South", "North", "South", "North", "South"],
        }
    )


def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test ReportAgent AI Enhancer")
    parser.add_argument("--csv", type=Path, default=None, help="Optional CSV path")
    parser.add_argument("--no-ai", action="store_true", help="Force heuristic mode")
    args = parser.parse_args()

    if args.no_ai:
        os.environ["AI_ENHANCER_ENABLED"] = "false"

    df = load_csv(args.csv) if args.csv else build_sample_df()
    enhancer = AIEnhancer()

    print("==> detect_column_types")
    cols = enhancer.detect_column_types(df)
    print(json.dumps(cols, ensure_ascii=False, indent=2))

    if cols.get("numeric"):
        x, y = cols["category"][0] if cols.get("category") else cols["numeric"][0], cols["numeric"][0]
        print("\n==> suggest_chart_type", enhancer.suggest_chart_type(df, x, y))
        print("==> suggest_chart_title", enhancer.suggest_chart_title(df, x, y))

    print("\n==> analyze_dataframe")
    result = enhancer.analyze_dataframe(df)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    for key in ("columns", "suggested_charts", "description", "insights"):
        assert key in result, f"Missing key: {key}"

    print("\n✅ Test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
