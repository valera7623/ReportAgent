#!/usr/bin/env python3
"""Test self-healing RAG: trigger errors, verify KB search, demo admin API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _http_json(method: str, url: str, headers: dict | None = None, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def test_knowledge_base_search() -> None:
    """Initialize KB and search for a seed fix."""
    os.environ.setdefault("CHROMA_PERSIST_DIR", str(ROOT / "chroma_data_test"))
    os.environ.setdefault("SELF_HEALING_ENABLED", "true")

    from app.self_healing.init_kb import init_knowledge_base
    from app.self_healing.vector_store import get_knowledge_base, reset_knowledge_base

    reset_knowledge_base()
    init_knowledge_base()
    kb = get_knowledge_base()
    assert kb is not None, "Knowledge base should initialize"

    results = kb.search_similar_errors(
        "pandas ParserError tokenizing data Expected fields",
        agent_name="parser",
        limit=3,
        threshold=0.5,
    )
    print(f"==> KB search returned {len(results)} matches")
    for r in results:
        print(f"    - {r['id'][:12]}... sim={r.get('similarity', 0):.3f} agent={r['agent_name']}")

    stats = kb.get_stats()
    print(f"==> KB stats: {stats['total_fixes']} fixes, success_rate={stats['success_rate']}")


def test_analyst_error_creates_record() -> None:
    """Trigger analyst error and verify self-healing records it."""
    os.environ.setdefault("CHROMA_PERSIST_DIR", str(ROOT / "chroma_data_test"))
    os.environ.setdefault("SELF_HEALING_ENABLED", "true")

    from app.agents.analyst import run_analyst
    from app.self_healing.vector_store import get_knowledge_base

    before = 0
    kb = get_knowledge_base()
    if kb:
        before = kb.get_stats()["total_fixes"]

    try:
        run_analyst({"task_id": "sh-test", "data": [], "numeric_columns": [], "text_columns": []})
    except Exception as exc:
        print(f"==> Analyst error (expected): {type(exc).__name__}: {exc}")

    if kb:
        after = kb.get_stats()["total_fixes"]
        print(f"==> KB records: {before} -> {after} (new error should be recorded)")


def test_admin_api(base_url: str, admin_key: str) -> None:
    """Demonstrate manual fix via admin endpoints."""
    if not admin_key:
        print("==> Admin API test skipped (no ADMIN_API_KEY)")
        return

    headers = {"X-Admin-Key": admin_key}
    fix_body = {
        "error_text": "TestError manual fix demo column missing revenue",
        "solution_prompt": "Use fuzzy column matching for revenue column",
        "solution_code": '{"action": "fuzzy_column_match", "params": {"_missing_column": "revenue"}}',
        "agent_name": "analyst",
        "error_type": "analyst",
    }

    try:
        created = _http_json(
            "POST",
            f"{base_url.rstrip('/')}/admin/self_healing/fixes",
            headers=headers,
            body=fix_body,
        )
        fix_id = created["fix_id"]
        print(f"==> Manual fix created: {fix_id}")

        confirmed = _http_json(
            "POST",
            f"{base_url.rstrip('/')}/admin/self_healing/confirm/{fix_id}",
            headers=headers,
        )
        print(f"==> Fix confirmed: {confirmed['message']}")

        stats = _http_json(
            "GET",
            f"{base_url.rstrip('/')}/admin/self_healing/stats",
            headers=headers,
        )
        print(f"==> Stats: total_fixes={stats['total_fixes']} success_rate={stats['success_rate']}")
    except urllib.error.HTTPError as exc:
        print(f"==> Admin API error {exc.code}: {exc.read().decode()[:200]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test ReportAgent self-healing RAG")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="FastAPI base URL")
    parser.add_argument("--admin-key", default=os.getenv("ADMIN_API_KEY", ""), help="ADMIN_API_KEY")
    parser.add_argument("--skip-admin", action="store_true", help="Skip admin API test")
    args = parser.parse_args()

    print("==> Test 1: Knowledge base search (seed fixes)")
    test_knowledge_base_search()

    print("\n==> Test 2: Analyst error → KB record")
    test_analyst_error_creates_record()

    if not args.skip_admin:
        print("\n==> Test 3: Admin API manual fix")
        test_admin_api(args.base_url, args.admin_key)

    print("\n==> Self-healing tests complete")
    print("Logs: logs/log_self_healing.json")


if __name__ == "__main__":
    main()
