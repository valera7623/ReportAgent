"""Fire report webhooks in background without blocking Celery tasks."""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

from app.db.database import log_history
from app.utils.logger import get_logger
from app.utils.metrics import hash_user_id
from app.webhook.config import (
    WEBHOOK_ENABLED,
    WEBHOOK_FAILURE_DEACTIVATE_THRESHOLD,
    WEBHOOK_MAX_CONCURRENT,
    WEBHOOK_PUBLIC_BASE_URL,
)
from app.webhook.registration import (
    deactivate_webhook,
    get_webhooks_for_event,
    notify_user_webhook_deactivated,
    record_webhook_failure,
    record_webhook_success,
)
from app.webhook.sender import WebhookSender

logger = get_logger("webhook_dispatcher", "log_webhook.log")

_executor = ThreadPoolExecutor(max_workers=WEBHOOK_MAX_CONCURRENT, thread_name_prefix="webhook")


def _public_base_url() -> str:
    base = WEBHOOK_PUBLIC_BASE_URL
    if base:
        return base
    domain = os.getenv("DOMAIN", "localhost").strip()
    if domain.startswith("http"):
        return domain.rstrip("/")
    return f"https://{domain}"


def build_webhook_payload(
    *,
    event: str,
    task_id: str,
    status: str,
    user_id: str | None,
    output_format: str | None = None,
    download_path: str | None = None,
    error_message: str | None = None,
    source_type: str = "unknown",
    duration_seconds: float | None = None,
    retry_count: int = 0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": event,
        "task_id": task_id,
        "status": status,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "user_id": hash_user_id(user_id),
        "metadata": {
            "source_type": source_type,
            "duration_seconds": round(duration_seconds, 2) if duration_seconds is not None else None,
            "retry_count": retry_count,
        },
    }
    if output_format:
        payload["output_format"] = output_format
    if status == "SUCCESS" and download_path:
        payload["download_url"] = f"{_public_base_url()}{download_path}"
    if status == "FAILURE" and error_message:
        payload["error_message"] = error_message[:1000]
    return payload


def _deliver_one(
    webhook: dict[str, Any],
    payload: dict[str, Any],
    task_id: str,
    user_id: str | None,
) -> None:
    sender = WebhookSender()
    success = sender.send_webhook_sync(
        webhook["url"],
        payload,
        task_id,
        secret=webhook.get("secret"),
        webhook_id=webhook["id"],
    )

    if success:
        record_webhook_success(webhook["id"])
        if user_id:
            log_history(
                user_id,
                f"webhook_sent event={payload.get('event')} id={webhook['id'][:8]}",
                task_id,
                request_type="webhook_sent",
            )
        return

    failures = record_webhook_failure(webhook["id"])
    if failures > WEBHOOK_FAILURE_DEACTIVATE_THRESHOLD:
        deactivate_webhook(webhook["id"])
        logger.error(
            "Deactivated webhook %s after %d failures (url=%s)",
            webhook["id"],
            failures,
            webhook["url"][:120],
        )
        if user_id:
            notify_user_webhook_deactivated(user_id, webhook["id"], webhook["url"])


def _dispatch_sync(
    event: str,
    task_id: str,
    payload: dict[str, Any],
    user_id: str | None,
) -> None:
    if not WEBHOOK_ENABLED or not user_id:
        return

    webhooks = get_webhooks_for_event(event, user_id=user_id, include_secret=True)
    if not webhooks:
        return

    logger.info("Dispatching %d webhook(s) for event=%s task=%s", len(webhooks), event, task_id)

    if len(webhooks) <= WEBHOOK_MAX_CONCURRENT:
        futures = [
            _executor.submit(_deliver_one, wh, payload, task_id, user_id)
            for wh in webhooks
        ]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as exc:
                logger.warning("Webhook delivery thread failed: %s", exc)
    else:
        for wh in webhooks:
            _deliver_one(wh, payload, task_id, user_id)


def fire_report_webhooks(
    *,
    event: str,
    task_id: str,
    user_id: str | None,
    payload: dict[str, Any],
) -> None:
    """Fire-and-forget webhook dispatch (non-blocking for Celery)."""
    if not WEBHOOK_ENABLED or not user_id:
        return

    thread = threading.Thread(
        target=_dispatch_sync,
        args=(event, task_id, payload, user_id),
        daemon=True,
        name=f"webhook-dispatch-{task_id[:8]}",
    )
    thread.start()


def fire_report_webhooks_and_wait(
    *,
    event: str,
    task_id: str,
    user_id: str | None,
    payload: dict[str, Any],
) -> None:
    """Synchronous dispatch (for tests)."""
    _dispatch_sync(event, task_id, payload, user_id)
