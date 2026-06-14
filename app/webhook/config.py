"""Webhook delivery configuration."""

from __future__ import annotations

import os

WEBHOOK_ENABLED = os.getenv("WEBHOOK_ENABLED", "true").lower() in ("1", "true", "yes")
WEBHOOK_TIMEOUT_SECONDS = float(os.getenv("WEBHOOK_TIMEOUT_SECONDS", "10"))
WEBHOOK_RETRY_COUNT = int(os.getenv("WEBHOOK_RETRY_COUNT", "3"))
WEBHOOK_RETRY_DELAY_SECONDS = float(os.getenv("WEBHOOK_RETRY_DELAY_SECONDS", "5"))
WEBHOOK_USER_AGENT = os.getenv("WEBHOOK_USER_AGENT", "ReportAgent-Webhook/1.0")
WEBHOOK_MAX_URL_LENGTH = int(os.getenv("WEBHOOK_MAX_URL_LENGTH", "500"))
WEBHOOK_MAX_CONCURRENT = int(os.getenv("WEBHOOK_MAX_CONCURRENT", "5"))
WEBHOOK_FAILURE_DEACTIVATE_THRESHOLD = int(os.getenv("WEBHOOK_FAILURE_DEACTIVATE_THRESHOLD", "5"))
WEBHOOK_PUBLIC_BASE_URL = os.getenv("WEBHOOK_PUBLIC_BASE_URL", "").strip().rstrip("/")

VALID_EVENTS = frozenset({"report.completed", "report.failed"})
