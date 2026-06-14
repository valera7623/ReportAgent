"""Deliver webhook HTTP POST requests with retries."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from app.utils.logger import get_logger
from app.utils.metrics import record_webhook_attempt, record_webhook_retry
from app.webhook.config import (
    WEBHOOK_ENABLED,
    WEBHOOK_RETRY_COUNT,
    WEBHOOK_RETRY_DELAY_SECONDS,
    WEBHOOK_TIMEOUT_SECONDS,
    WEBHOOK_USER_AGENT,
)
from app.webhook.signature import sign_payload

logger = get_logger("webhook_sender", "log_webhook.log")

_async_client: httpx.AsyncClient | None = None
_sync_client: httpx.Client | None = None


def _build_headers(payload: dict[str, Any], task_id: str, secret: str | None) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": WEBHOOK_USER_AGENT,
        "X-ReportAgent-Task-Id": task_id,
    }
    if secret:
        headers["X-Webhook-Signature"] = sign_payload(secret, payload)
    return headers


def _get_sync_client() -> httpx.Client:
    global _sync_client
    if _sync_client is None:
        _sync_client = httpx.Client(
            timeout=WEBHOOK_TIMEOUT_SECONDS,
            headers={"User-Agent": WEBHOOK_USER_AGENT},
            follow_redirects=False,
        )
    return _sync_client


async def _get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None:
        _async_client = httpx.AsyncClient(
            timeout=WEBHOOK_TIMEOUT_SECONDS,
            headers={"User-Agent": WEBHOOK_USER_AGENT},
            follow_redirects=False,
        )
    return _async_client


def _deliver_sync(
    url: str,
    body: str,
    headers: dict[str, str],
    *,
    event: str,
    task_id: str,
    webhook_id: str | None,
) -> bool:
    client = _get_sync_client()
    max_attempts = WEBHOOK_RETRY_COUNT + 1
    delay = WEBHOOK_RETRY_DELAY_SECONDS

    for attempt in range(1, max_attempts + 1):
        started = time.perf_counter()
        try:
            response = client.post(url, content=body, headers=headers)
            duration = time.perf_counter() - started
            success = 200 <= response.status_code < 300
            record_webhook_attempt(event, success, duration)

            logger.info(
                "webhook delivery task=%s webhook=%s url=%s attempt=%d status=%d success=%s",
                task_id,
                webhook_id or "-",
                url[:120],
                attempt,
                response.status_code,
                success,
            )
            if success:
                return True

            logger.warning(
                "webhook non-2xx task=%s attempt=%d status=%d",
                task_id,
                attempt,
                response.status_code,
            )
        except Exception as exc:
            duration = time.perf_counter() - started
            record_webhook_attempt(event, False, duration)
            logger.warning("webhook error task=%s attempt=%d: %s", task_id, attempt, exc)

        if attempt < max_attempts:
            record_webhook_retry(event)
            sleep_for = delay * (2 ** (attempt - 1))
            time.sleep(sleep_for)

    return False


async def _deliver_async(
    url: str,
    body: str,
    headers: dict[str, str],
    *,
    event: str,
    task_id: str,
    webhook_id: str | None,
) -> bool:
    client = await _get_async_client()
    max_attempts = WEBHOOK_RETRY_COUNT + 1
    delay = WEBHOOK_RETRY_DELAY_SECONDS

    for attempt in range(1, max_attempts + 1):
        started = time.perf_counter()
        try:
            response = await client.post(url, content=body, headers=headers)
            duration = time.perf_counter() - started
            success = 200 <= response.status_code < 300
            record_webhook_attempt(event, success, duration)

            logger.info(
                "webhook delivery task=%s webhook=%s url=%s attempt=%d status=%d success=%s",
                task_id,
                webhook_id or "-",
                url[:120],
                attempt,
                response.status_code,
                success,
            )
            if success:
                return True
        except Exception as exc:
            duration = time.perf_counter() - started
            record_webhook_attempt(event, False, duration)
            logger.warning("webhook error task=%s attempt=%d: %s", task_id, attempt, exc)

        if attempt < max_attempts:
            record_webhook_retry(event)
            await asyncio.sleep(delay * (2 ** (attempt - 1)))

    return False


class WebhookSender:
    """Send signed webhook POST requests with exponential backoff retries."""

    async def send_webhook(
        self,
        url: str,
        payload: dict[str, Any],
        task_id: str,
        *,
        secret: str | None = None,
        webhook_id: str | None = None,
    ) -> bool:
        if not WEBHOOK_ENABLED:
            return False

        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        headers = _build_headers(payload, task_id, secret)
        return await _deliver_async(
            url,
            body,
            headers,
            event=str(payload.get("event", "unknown")),
            task_id=task_id,
            webhook_id=webhook_id,
        )

    def send_webhook_sync(
        self,
        url: str,
        payload: dict[str, Any],
        task_id: str,
        *,
        secret: str | None = None,
        webhook_id: str | None = None,
    ) -> bool:
        if not WEBHOOK_ENABLED:
            return False

        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        headers = _build_headers(payload, task_id, secret)
        return _deliver_sync(
            url,
            body,
            headers,
            event=str(payload.get("event", "unknown")),
            task_id=task_id,
            webhook_id=webhook_id,
        )
