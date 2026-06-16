"""Redis-backed preview cache with in-memory fallback."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import redis

from app.utils.logger import get_logger

logger = get_logger("preview_cache", "log_api.log")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
PREVIEW_TTL_SECONDS = int(os.getenv("PREVIEW_TTL_SECONDS", "3600"))
PREVIEW_DIR = Path(os.getenv("PREVIEW_DIR", "/app/storage/temp"))

_memory_store: dict[str, tuple[float, dict[str, Any]]] = {}
_memory_charts: dict[str, tuple[float, bytes]] = {}
_redis_client: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=False)
    return _redis_client


def _preview_key(preview_id: str) -> str:
    return f"preview:{preview_id}"


def _chart_key(preview_id: str, chart_index: int) -> str:
    return f"preview_chart:{preview_id}:{chart_index}"


def _job_key(job_id: str) -> str:
    return f"preview_job:{job_id}"


def preview_storage_dir(preview_id: str) -> Path:
    path = PREVIEW_DIR / preview_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def store_preview(preview_id: str, data: dict[str, Any], user_id: str) -> None:
    """Store preview metadata (user-scoped)."""
    payload = {
        **data,
        "preview_id": preview_id,
        "user_id": user_id,
        "stored_at": time.time(),
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        _redis().setex(_preview_key(preview_id), PREVIEW_TTL_SECONDS, raw)
    except Exception as exc:
        logger.warning("Redis store_preview failed, using memory: %s", exc)
        _memory_store[preview_id] = (time.time() + PREVIEW_TTL_SECONDS, payload)


def get_preview(preview_id: str) -> dict[str, Any] | None:
    try:
        raw = _redis().get(_preview_key(preview_id))
        if raw:
            return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        logger.warning("Redis get_preview failed: %s", exc)

    entry = _memory_store.get(preview_id)
    if not entry:
        return None
    expires_at, payload = entry
    if time.time() > expires_at:
        _memory_store.pop(preview_id, None)
        return None
    return payload


def delete_preview(preview_id: str) -> None:
    try:
        client = _redis()
        client.delete(_preview_key(preview_id))
        for key in client.scan_iter(match=f"preview_chart:{preview_id}:*"):
            client.delete(key)
    except Exception as exc:
        logger.warning("Redis delete_preview failed: %s", exc)

    _memory_store.pop(preview_id, None)
    keys_to_drop = [k for k in _memory_charts if k.startswith(f"preview_chart:{preview_id}:")]
    for k in keys_to_drop:
        _memory_charts.pop(k, None)

    preview_path = PREVIEW_DIR / preview_id
    if preview_path.is_dir():
        shutil.rmtree(preview_path, ignore_errors=True)


def store_chart_png(preview_id: str, chart_index: int, png_bytes: bytes) -> None:
    chart_path = preview_storage_dir(preview_id) / f"chart_{chart_index}.png"
    chart_path.write_bytes(png_bytes)
    key = _chart_key(preview_id, chart_index)
    try:
        _redis().setex(key, PREVIEW_TTL_SECONDS, png_bytes)
    except Exception as exc:
        logger.warning("Redis store_chart failed: %s", exc)
        _memory_charts[key] = (time.time() + PREVIEW_TTL_SECONDS, png_bytes)


def get_chart_png(preview_id: str, chart_index: int) -> bytes | None:
    chart_path = PREVIEW_DIR / preview_id / f"chart_{chart_index}.png"
    if chart_path.is_file():
        return chart_path.read_bytes()

    key = _chart_key(preview_id, chart_index)
    try:
        raw = _redis().get(key)
        if raw:
            return raw
    except Exception as exc:
        logger.warning("Redis get_chart failed: %s", exc)

    entry = _memory_charts.get(key)
    if not entry:
        return None
    expires_at, data = entry
    if time.time() > expires_at:
        _memory_charts.pop(key, None)
        return None
    return data


def store_job_result(job_id: str, payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        _redis().setex(_job_key(job_id), PREVIEW_TTL_SECONDS, raw)
    except Exception as exc:
        logger.warning("Redis store_job failed: %s", exc)
        _memory_store[f"job:{job_id}"] = (time.time() + PREVIEW_TTL_SECONDS, payload)


def get_job_result(job_id: str) -> dict[str, Any] | None:
    try:
        raw = _redis().get(_job_key(job_id))
        if raw:
            return json.loads(raw.decode("utf-8"))
    except Exception as exc:
        logger.warning("Redis get_job failed: %s", exc)
    entry = _memory_store.get(f"job:{job_id}")
    if not entry:
        return None
    expires_at, payload = entry
    if time.time() > expires_at:
        _memory_store.pop(f"job:{job_id}", None)
        return None
    return payload


def cleanup_expired() -> int:
    """Remove expired previews from disk and Redis keys."""
    removed = 0
    if PREVIEW_DIR.is_dir():
        cutoff = time.time() - PREVIEW_TTL_SECONDS
        for child in PREVIEW_DIR.iterdir():
            if not child.is_dir():
                continue
            try:
                mtime = child.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                preview_id = child.name
                delete_preview(preview_id)
                removed += 1

    now = time.time()
    for pid in list(_memory_store.keys()):
        if pid.startswith("job:"):
            continue
        entry = _memory_store.get(pid)
        if entry and now > entry[0]:
            _memory_store.pop(pid, None)
            removed += 1

    for key in list(_memory_charts.keys()):
        entry = _memory_charts.get(key)
        if entry and now > entry[0]:
            _memory_charts.pop(key, None)
            removed += 1

    return removed
