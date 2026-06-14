#!/usr/bin/env python3
"""Test webhook registration, signature, and delivery."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_received: list[dict] = []


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode()
        payload = json.loads(body)
        _received.append({"headers": dict(self.headers), "payload": payload})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_args) -> None:
        return


def _http_json(method: str, url: str, headers: dict | None = None, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def test_signature_unit() -> None:
    from app.webhook.signature import sign_payload, verify_signature

    payload = {"event": "report.completed", "task_id": "abc"}
    secret = "test-secret"
    sig = sign_payload(secret, payload)
    assert verify_signature(secret, payload, sig)
    assert not verify_signature(secret, payload, "bad")
    print("==> Signature unit test OK")


def test_url_validation() -> None:
    from app.webhook.url_validator import validate_webhook_url

    validate_webhook_url("https://example.com/hook")
    try:
        validate_webhook_url("http://127.0.0.1/hook")
        raise AssertionError("should block localhost")
    except ValueError:
        pass
    print("==> URL validation OK")


def test_delivery_sync() -> None:
    os.environ.setdefault("WEBHOOK_ENABLED", "true")
    os.environ.setdefault("WEBHOOK_RETRY_COUNT", "1")

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    from app.webhook.dispatcher import build_webhook_payload, fire_report_webhooks_and_wait
    from app.webhook.sender import WebhookSender

    url = f"http://127.0.0.1:{port}/hook"
    payload = build_webhook_payload(
        event="report.completed",
        task_id="test-task",
        status="SUCCESS",
        user_id="user-123",
        output_format="pdf",
        download_path="/tasks/test-task/pdf",
        source_type="file",
        duration_seconds=1.2,
    )

    sender = WebhookSender()
    ok = sender.send_webhook_sync(url, payload, "test-task", secret="s3cret")
    assert ok, "direct send should succeed"
    assert _received, "mock server should receive payload"
    print(f"==> Direct delivery OK: {_received[-1]['payload'].get('event')}")

    _received.clear()
    fire_report_webhooks_and_wait(
        event="report.completed",
        task_id="test-task-2",
        user_id=None,
        payload=payload,
    )
    server.shutdown()


def test_api_registration(base_url: str, api_key: str) -> None:
    if not api_key:
        print("==> API registration test skipped (no API key)")
        return

    headers = {"X-API-Key": api_key}
    created = _http_json(
        "POST",
        f"{base_url.rstrip('/')}/api/webhooks/register",
        headers=headers,
        body={
            "url": "https://example.com/report-callback",
            "events": ["report.completed", "report.failed"],
            "secret": "demo-secret",
        },
    )
    webhook_id = created["webhook_id"]
    print(f"==> Registered webhook: {webhook_id}")

    listed = _http_json("GET", f"{base_url.rstrip('/')}/api/webhooks", headers=headers)
    print(f"==> User has {len(listed)} webhook(s)")

    _http_json(
        "DELETE",
        f"{base_url.rstrip('/')}/api/webhooks/{webhook_id}",
        headers=headers,
    )
    print("==> Deleted test webhook")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test ReportAgent webhooks")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=os.getenv("API_KEY", ""))
    parser.add_argument("--skip-api", action="store_true")
    args = parser.parse_args()

    test_signature_unit()
    test_url_validation()
    test_delivery_sync()

    if not args.skip_api:
        test_api_registration(args.base_url, args.api_key)

    print("\n==> Webhook tests complete")


if __name__ == "__main__":
    main()
