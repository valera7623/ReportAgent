"""Redis-based sliding-window rate limiting."""

from __future__ import annotations

import os
import time

import redis

from app.db.admin_queries import GLOBAL_SCOPE, get_global_rate_limit, get_user_rate_limit
from app.utils.logger import get_logger

logger = get_logger("rate_limiter", "log_api.log")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DEFAULT_USER_LIMIT = int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "100"))
ADMIN_RATE_LIMIT = int(os.getenv("ADMIN_RATE_LIMIT_REQUESTS_PER_MINUTE", "60"))
WINDOW_SECONDS = 60

_redis_client: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def _resolve_limit(user_id: str | None) -> int:
    if user_id:
        user_limit = get_user_rate_limit(user_id)
        if user_limit is not None:
            return user_limit
    try:
        return get_global_rate_limit()
    except Exception:
        return DEFAULT_USER_LIMIT


def check_rate_limit(user_id: str | None, *, is_admin: bool = False) -> bool:
    """
    Return True if request is allowed, False if rate limit exceeded.

    Uses Redis sorted set sliding window (per minute).
    """
    limit = ADMIN_RATE_LIMIT if is_admin else _resolve_limit(user_id)
    scope = f"admin:{user_id or 'anon'}" if is_admin else f"user:{user_id or 'anon'}"
    key = f"rate_limit:{scope}"

    now = time.time()
    window_start = now - WINDOW_SECONDS

    try:
        client = _redis()
        pipe = client.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, WINDOW_SECONDS + 5)
        _, _, count, _ = pipe.execute()
        return int(count) <= limit
    except Exception as exc:
        logger.warning("Rate limit check failed (allowing request): %s", exc)
        return True


def get_rate_limit_status(user_id: str | None) -> dict[str, int]:
    """Return current usage and limit for a scope."""
    limit = _resolve_limit(user_id)
    scope = f"user:{user_id or 'anon'}"
    key = f"rate_limit:{scope}"
    now = time.time()
    window_start = now - WINDOW_SECONDS
    try:
        client = _redis()
        client.zremrangebyscore(key, 0, window_start)
        used = int(client.zcard(key))
    except Exception:
        used = 0
    return {"limit": limit, "used": used, "remaining": max(0, limit - used)}
