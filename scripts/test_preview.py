#!/usr/bin/env python3
"""Test report preview flow: upload → preview → confirm."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

DEFAULT_BASE = "http://localhost:8000"
SAMPLE = Path(__file__).resolve().parent.parent / "app" / "samples" / "sample_sales.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description="Test ReportAgent preview API")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--api-key", default=os.getenv("API_KEY", ""))
    parser.add_argument("--email", default="preview-test@example.com")
    args = parser.parse_args()

    if not args.api_key:
        print("Set API_KEY or pass --api-key")
        return 1

    base = args.base_url.rstrip("/")
    headers = {"X-API-Key": args.api_key}
    print(f"=== Preview test ({base}) ===\n")

    if not SAMPLE.is_file():
        print(f"Sample not found: {SAMPLE}")
        return 1

    with httpx.Client(timeout=120.0) as client:
        print("1. POST /api/reports/preview")
        with SAMPLE.open("rb") as f:
            resp = client.post(
                f"{base}/api/reports/preview",
                headers=headers,
                files={"file": ("sample_sales.csv", f, "text/csv")},
            )
        print(f"   Status: {resp.status_code}")
        if resp.status_code not in (200, 201, 202):
            print(resp.text)
            return 1

        body = resp.json()
        if body.get("status") == "processing":
            job_id = body["job_id"]
            print(f"   Async job: {job_id}")
            for _ in range(60):
                time.sleep(2)
                st = client.get(f"{base}/api/reports/preview/status/{job_id}", headers=headers)
                job = st.json()
                if job.get("status") == "ready":
                    body = job
                    break
                if job.get("status") == "failed":
                    print(f"   Failed: {job}")
                    return 1
            else:
                print("   Timeout waiting for preview")
                return 1

        preview_id = body["preview_id"]
        data = body.get("data") or {}
        print(f"   preview_id: {preview_id}")
        print(f"   rows: {len(data.get('rows', []))} / {data.get('total_rows')}")
        print(f"   charts: {len(data.get('charts', []))}")
        print(f"   summary: {data.get('summary')}\n")

        if data.get("charts"):
            chart_url = data["charts"][0]["image_url"]
            print(f"2. GET {chart_url}")
            cr = client.get(f"{base}{chart_url}", headers=headers)
            print(f"   Status: {cr.status_code}, bytes: {len(cr.content)}\n")

        print("3. POST /api/reports/preview/confirm (download, no email)")
        resp = client.post(
            f"{base}/api/reports/preview/confirm",
            headers=headers,
            json={"preview_id": preview_id, "output_format": "pdf"},
        )
        print(f"   Status: {resp.status_code}")
        if resp.status_code not in (200, 202):
            print(resp.text)
            return 1
        task = resp.json()
        print(f"   task_id: {task.get('task_id')}")
        print(f"   download_url: {task.get('download_url')}\n")

    print("Preview test completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
