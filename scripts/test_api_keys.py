#!/usr/bin/env python3
"""Test API key management: list, revoke, rotate, and last-key protection."""

from __future__ import annotations

import argparse
import sys

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"


def _headers(api_key: str) -> dict[str, str]:
    return {"X-API-Key": api_key}


def main() -> int:
    parser = argparse.ArgumentParser(description="Test ReportAgent API key management")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    print(f"=== API Key Management Test ({base}) ===\n")

    with httpx.Client(timeout=30.0) as client:
        print("0. Onboarding: create user + first key (POST /api/keys/generate)")
        resp = client.post(
            f"{base}/api/keys/generate",
            json={"name": "Bootstrap", "email": "keys-test@example.com"},
        )
        if resp.status_code not in (200, 201):
            print(f"   FAIL: {resp.status_code} {resp.text}")
            return 1
        bootstrap = resp.json()
        key0 = bootstrap["key"]
        user_id = bootstrap.get("user_id")
        print(f"   user_id={user_id}, prefix={bootstrap['key_prefix']}\n")

        keys_created: list[tuple[str, str]] = [(bootstrap["id"], key0)]

        for i in range(1, 3):
            print(f"{i}. Generate key #{i + 1} (POST /api/keys/generate)")
            resp = client.post(
                f"{base}/api/keys/generate",
                headers=_headers(key0),
                json={"name": f"Key-{i + 1}"},
            )
            if resp.status_code not in (200, 201):
                print(f"   FAIL: {resp.status_code} {resp.text}")
                return 1
            data = resp.json()
            keys_created.append((data["id"], data["key"]))
            print(f"   id={data['id']}, prefix={data['key_prefix']}, name={data['name']}\n")

        print("3. List keys (GET /api/keys)")
        resp = client.get(f"{base}/api/keys", headers=_headers(key0))
        if resp.status_code != 200:
            print(f"   FAIL: {resp.status_code} {resp.text}")
            return 1
        listed = resp.json()["keys"]
        print(f"   Found {len(listed)} key(s):")
        for item in listed:
            current = " [current]" if item.get("is_current") else ""
            active = "active" if item["is_active"] else "revoked"
            print(f"   - {item['key_prefix']} ({item['name']}) {active}{current}")
        print()

        revoke_id, revoke_key = keys_created[1]
        print(f"4. Revoke key {revoke_id[:8]}… (DELETE /api/keys/{{id}})")
        resp = client.delete(f"{base}/api/keys/{revoke_id}", headers=_headers(key0))
        if resp.status_code != 200:
            print(f"   FAIL: {resp.status_code} {resp.text}")
            return 1
        print(f"   {resp.json()}\n")

        print("5. Verify revoked key no longer works (GET /api/keys)")
        resp = client.get(f"{base}/api/keys", headers=_headers(revoke_key))
        if resp.status_code == 401:
            print("   OK: revoked key rejected with 401\n")
        else:
            print(f"   FAIL: expected 401, got {resp.status_code}\n")
            return 1

        rotate_id, _rotate_key = keys_created[2]
        print(f"6. Rotate key {rotate_id[:8]}… (POST /api/keys/{{id}}/rotate)")
        resp = client.post(
            f"{base}/api/keys/{rotate_id}/rotate",
            headers=_headers(key0),
            json={"new_name": "Rotated Key"},
        )
        if resp.status_code != 200:
            print(f"   FAIL: {resp.status_code} {resp.text}")
            return 1
        rotated = resp.json()
        new_rotated_key = rotated["new_key"]
        print(f"   old={rotated['old_key_prefix']}, new_id={rotated['new_key_id']}\n")

        print("7. Verify rotated new key works (GET /api/keys)")
        resp = client.get(f"{base}/api/keys", headers=_headers(new_rotated_key))
        if resp.status_code != 200:
            print(f"   FAIL: {resp.status_code} {resp.text}")
            return 1
        print("   OK: new rotated key accepted\n")

        print("8. Revoke bootstrap key (still one active key remains)")
        bootstrap_id = keys_created[0][0]
        resp = client.delete(
            f"{base}/api/keys/{bootstrap_id}",
            headers=_headers(new_rotated_key),
        )
        if resp.status_code != 200:
            print(f"   FAIL: {resp.status_code} {resp.text}")
            return 1
        print(f"   {resp.json()}\n")

        print("9. Try to revoke last active key → expect 400")
        resp = client.get(f"{base}/api/keys", headers=_headers(new_rotated_key))
        active_ids = [k["id"] for k in resp.json()["keys"] if k["is_active"]]
        if len(active_ids) != 1:
            print(f"   FAIL: expected 1 active key, found {len(active_ids)}")
            return 1
        last_id = active_ids[0]
        resp = client.delete(
            f"{base}/api/keys/{last_id}",
            headers=_headers(new_rotated_key),
        )
        if resp.status_code == 400:
            print(f"   OK: {resp.json().get('detail')}\n")
        else:
            print(f"   FAIL: expected 400, got {resp.status_code} {resp.text}\n")
            return 1

    print("All API key management tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
