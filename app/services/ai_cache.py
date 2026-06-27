"""Redis cache for AI suggestions with in-memory fallback."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import redis

from app.utils.logger import get_logger

logger = get_logger("ai_cache", "log_api.log")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DEFAULT_TTL = int(os.getenv("AI_ENHANCER_CACHE_TTL", "86400"))

_redis_client: redis.Redis | None = None
_memory_store: dict[str, tuple[float, str]] = {}


def _redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


async def get(key: str) -> str | None:
    """Get cached JSON string by key."""
    try:
        value = _redis().get(key)
        if value is not None:
            return value
    except Exception as exc:
        logger.warning("Redis ai_cache get failed: %s", exc)

    entry = _memory_store.get(key)
    if not entry:
        return None
    expires_at, payload = entry
    if time.time() > expires_at:
        _memory_store.pop(key, None)
        return None
    return payload


async def set(key: str, value: str, ttl: int | None = None) -> None:
    """Store JSON string with TTL."""
    ttl_seconds = ttl if ttl is not None else DEFAULT_TTL
    try:
        _redis().setex(key, ttl_seconds, value)
        return
    except Exception as exc:
        logger.warning("Redis ai_cache set failed: %s", exc)

    _memory_store[key] = (time.time() + ttl_seconds, value)


def get_sync(key: str) -> dict[str, Any] | None:
    """Synchronous cache read for Celery agents."""
    try:
        raw = _redis().get(key)
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.warning("Redis ai_cache get_sync failed: %s", exc)

    entry = _memory_store.get(key)
    if not entry:
        return None
    expires_at, payload = entry
    if time.time() > expires_at:
        _memory_store.pop(key, None)
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def set_sync(key: str, payload: dict[str, Any], ttl: int | None = None) -> None:
    """Synchronous cache write for Celery agents."""
    ttl_seconds = ttl if ttl is not None else DEFAULT_TTL
    raw = json.dumps(payload, ensure_ascii=False)
    try:
        _redis().setex(key, ttl_seconds, raw)
        return
    except Exception as exc:
        logger.warning("Redis ai_cache set_sync failed: %s", exc)
    _memory_store[key] = (time.time() + ttl_seconds, raw)
