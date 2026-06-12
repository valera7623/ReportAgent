#!/usr/bin/env python3
"""Test observability: trigger agent error, print metrics, optionally ping Telegram."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def _fetch_metrics(base_url: str) -> str:
    url = f"{base_url.rstrip('/')}/metrics"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _print_metric_snippets(metrics_text: str) -> None:
    keywords = (
        "agent_errors_total",
        "agent_duration_seconds",
        "celery_queue_length",
        "voice_transcriptions_total",
        "active_users",
        "report_requests_total",
    )
    print("\n==> Metric samples")
    for line in metrics_text.splitlines():
        if line.startswith("#"):
            continue
        if any(k in line for k in keywords):
            print(f"  {line}")


def _trigger_agent_error() -> None:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from app.agents.analyst import run_analyst
    from app.utils.metrics import agent_errors_total

    before = agent_errors_total.labels(agent_name="analyst", error_type="AgentError")._value.get()  # noqa: SLF001

    try:
        run_analyst({"task_id": "test-alert", "data": [], "numeric_columns": [], "text_columns": []})
    except Exception:
        pass

    after = agent_errors_total.labels(agent_name="analyst", error_type="AgentError")._value.get()  # noqa: SLF001
    print(f"==> Triggered analyst error counter: {before} -> {after}")


def _send_test_telegram() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("==> Telegram test skipped (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set)")
        return

    domain = os.getenv("DOMAIN", "example.com")
    grafana_domain = os.getenv("GRAFANA_DOMAIN", f"grafana.{domain}")
    text = (
        "<b>ReportAgent test alert</b>\n"
        "Observability stack test from scripts/test_alerts.py\n"
        f'<a href="https://{grafana_domain}/d/ReportAgent-Main/reportagent-main">Open Grafana</a>'
    )
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
        if body.get("ok"):
            print("==> Telegram test message sent OK")
        else:
            print(f"==> Telegram API error: {body}")
    except urllib.error.HTTPError as exc:
        print(f"==> Telegram HTTP error: {exc.read().decode()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Test ReportAgent alerts and metrics")
    parser.add_argument(
        "--base-url",
        default=os.getenv("METRICS_BASE_URL", "http://localhost:8000"),
        help="FastAPI base URL for /metrics",
    )
    parser.add_argument("--skip-error", action="store_true", help="Do not trigger synthetic agent error")
    parser.add_argument("--telegram", action="store_true", help="Send test message to Telegram")
    args = parser.parse_args()

    if not args.skip_error:
        _trigger_agent_error()

    try:
        metrics = _fetch_metrics(args.base_url)
        print(f"==> Fetched /metrics from {args.base_url} ({len(metrics)} bytes)")
        _print_metric_snippets(metrics)
    except Exception as exc:
        print(f"ERROR: could not fetch metrics: {exc}", file=sys.stderr)
        return 1

    if args.telegram:
        _send_test_telegram()

    print("\n==> Done. Check Alertmanager/Grafana if alerts are configured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
