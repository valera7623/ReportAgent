#!/usr/bin/env python3
"""Test Admin API endpoints with ADMIN_API_KEY."""

from __future__ import annotations

import argparse
import os
import sys

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"


def admin_headers(key: str) -> dict[str, str]:
    return {"X-Admin-Key": key}


def main() -> int:
    parser = argparse.ArgumentParser(description="Test ReportAgent Admin API")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--admin-key", default=os.getenv("ADMIN_API_KEY", ""))
    args = parser.parse_args()

    if not args.admin_key:
        print("ERROR: set ADMIN_API_KEY env or pass --admin-key")
        return 1

    base = args.base_url.rstrip("/")
    hdrs = admin_headers(args.admin_key)
    print(f"=== Admin API test ({base}) ===\n")

    with httpx.Client(timeout=60.0) as client:
        print("1. Without admin key → expect 401")
        resp = client.get(f"{base}/admin/health/all")
        if resp.status_code == 401:
            print("   OK: 401 Unauthorized\n")
        else:
            print(f"   FAIL: expected 401, got {resp.status_code}\n")
            return 1

        print("2. GET /admin/health/all")
        resp = client.get(f"{base}/admin/health/all", headers=hdrs)
        print(f"   Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"   Error: {resp.text}")
            return 1
        health = resp.json()
        print(f"   Overall: {health.get('status')}\n")

        print("3. GET /admin/health/system")
        resp = client.get(f"{base}/admin/health/system", headers=hdrs)
        print(f"   Status: {resp.status_code}\n")

        print("4. POST /api/keys/generate (create test user)")
        resp = client.post(
            f"{base}/api/keys/generate",
            json={"email": "admin-test@example.com", "name": "AdminTest"},
        )
        if resp.status_code not in (200, 201):
            print(f"   FAIL: {resp.text}")
            return 1
        user = resp.json()
        user_id = user["user_id"]
        print(f"   user_id: {user_id}\n")

        print("5. GET /admin/users")
        resp = client.get(f"{base}/admin/users?limit=5", headers=hdrs)
        print(f"   Status: {resp.status_code}, total={resp.json().get('total')}\n")

        print("6. GET /admin/users/{id}")
        resp = client.get(f"{base}/admin/users/{user_id}", headers=hdrs)
        print(f"   Status: {resp.status_code}\n")

        print("7. POST /admin/users/{id}/block")
        resp = client.post(f"{base}/admin/users/{user_id}/block", headers=hdrs)
        print(f"   Status: {resp.status_code}, body={resp.json()}\n")
        if resp.status_code != 200:
            return 1

        print("8. Verify blocked user API key rejected")
        user_key = user["key"]
        resp = client.get(f"{base}/api/preferences", headers={"X-API-Key": user_key})
        if resp.status_code == 401:
            print("   OK: blocked user cannot authenticate\n")
        else:
            print(f"   WARN: expected 401, got {resp.status_code}\n")

        print("9. POST /admin/users/{id}/unblock")
        resp = client.post(f"{base}/admin/users/{user_id}/unblock", headers=hdrs)
        print(f"   Status: {resp.status_code}, body={resp.json()}\n")

        print("10. GET /admin/celery/status")
        resp = client.get(f"{base}/admin/celery/status", headers=hdrs)
        print(f"   Status: {resp.status_code}, queue={resp.json().get('queue_length')}\n")

        print("11. GET /admin/logs?limit=10")
        resp = client.get(f"{base}/admin/logs?limit=10", headers=hdrs)
        print(f"   Status: {resp.status_code}, entries={len(resp.json().get('logs', []))}\n")

        print("12. GET /admin/metrics/summary")
        resp = client.get(f"{base}/admin/metrics/summary", headers=hdrs)
        print(f"   Status: {resp.status_code}\n")

        print("13. GET /admin/rate-limits")
        resp = client.get(f"{base}/admin/rate-limits", headers=hdrs)
        print(f"   Status: {resp.status_code}, global={resp.json().get('global_limit')}\n")

        print("14. DELETE /admin/users/{id}")
        resp = client.delete(f"{base}/admin/users/{user_id}", headers=hdrs)
        print(f"   Status: {resp.status_code}, body={resp.json()}\n")

    print("All admin API tests completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
