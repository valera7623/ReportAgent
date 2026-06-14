#!/usr/bin/env python3
"""Minimal webhook receiver for local testing (stdlib only)."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class WebhookHandler(BaseHTTPRequestHandler):
    secret: str | None = None

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        signature = self.headers.get("X-Webhook-Signature", "")

        print("\n=== Incoming webhook ===")
        print(f"Path: {self.path}")
        print(f"Signature: {signature or '(none)'}")

        try:
            payload = json.loads(body)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            print(body)
            payload = {}

        if self.secret and signature:
            expected = hmac.new(
                self.secret.encode(),
                json.dumps(payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True).encode(),
                hashlib.sha256,
            ).hexdigest()
            ok = hmac.compare_digest(expected, signature)
            print(f"Signature valid: {ok}")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock webhook receiver")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--secret", default="", help="Optional HMAC secret for verification demo")
    args = parser.parse_args()

    WebhookHandler.secret = args.secret or None
    server = HTTPServer((args.host, args.port), WebhookHandler)
    print(f"Mock webhook server listening on http://{args.host}:{args.port}/")
    print("Register with: POST /api/webhooks/register {\"url\": \"http://HOST:PORT/\"}")
    server.serve_forever()


if __name__ == "__main__":
    main()
