#!/usr/bin/env python3
"""Demonstrate API key generation, preferences, and report generation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
SAMPLE_CSV = Path(__file__).resolve().parent.parent / "app" / "samples" / "sample_sales.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description="Test ReportAgent API key flow")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    parser.add_argument("--email", default="demo@example.com", help="Email for new API key")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    print(f"=== ReportAgent API key test ({base}) ===\n")

    with httpx.Client(timeout=60.0) as client:
        print("1. Generate API key (POST /api/keys/generate)")
        resp = client.post(f"{base}/api/keys/generate", json={"email": args.email})
        print(f"   Status: {resp.status_code}")
        if resp.status_code not in (200, 201):
            print(f"   Error: {resp.text}")
            return 1

        payload = resp.json()
        api_key = payload.get("key") or payload.get("api_key")
        user_id = payload.get("user_id")
        print(f"   user_id: {user_id}")
        print(f"   api_key: ****{api_key[-4:]}\n")

        headers = {"X-API-Key": api_key}

        print("2. Get preferences (GET /api/preferences)")
        resp = client.get(f"{base}/api/preferences", headers=headers)
        print(f"   Status: {resp.status_code}")
        print(f"   Body: {resp.json()}\n")

        print("3. Update preferences (PUT /api/preferences)")
        resp = client.put(
            f"{base}/api/preferences",
            headers=headers,
            json={"theme": "dark", "preferred_chart_type": "pie", "default_email": args.email},
        )
        print(f"   Status: {resp.status_code}")
        print(f"   Body: {resp.json()}\n")

        if not SAMPLE_CSV.is_file():
            print(f"Sample CSV not found: {SAMPLE_CSV}")
            return 1

        print("4. Generate report (POST /generate_report)")
        with SAMPLE_CSV.open("rb") as f:
            resp = client.post(
                f"{base}/generate_report",
                headers=headers,
                files={"file": ("sample_sales.csv", f, "text/csv")},
            )
        print(f"   Status: {resp.status_code}")
        if resp.status_code != 202:
            print(f"   Error: {resp.text}")
            return 1

        report = resp.json()
        print(f"   task_id: {report.get('task_id')}")
        print(f"   user_id: {report.get('user_id')}")
        print(f"   usage_count: {report.get('usage_count')}")
        print(f"   download_url: {report.get('download_url')}\n")

    print("All steps completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
