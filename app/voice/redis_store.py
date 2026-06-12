"""Redis storage for voice clarification state."""

from __future__ import annotations

import json
import os
from typing import Any

import redis

PARTIAL_KEY = "voice:partial:{task_id}"
STATUS_KEY = "voice:status:{task_id}"
TTL_SECONDS = int(os.getenv("VOICE_PARTIAL_TTL", "86400"))


def _client() -> redis.Redis:
    url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return redis.from_url(url, decode_responses=True)


def save_partial_state(
    task_id: str,
    *,
    user_id: str | None,
    api_key: str | None,
    audio_path: str,
    transcript: str,
    partial_intent: dict[str, Any],
    clarification_question: str,
    email: str | None = None,
) -> None:
    payload = {
        "user_id": user_id,
        "api_key": api_key,
        "audio_path": audio_path,
        "transcript": transcript,
        "partial_intent": partial_intent,
        "clarification_question": clarification_question,
        "email": email,
    }
    client = _client()
    client.setex(PARTIAL_KEY.format(task_id=task_id), TTL_SECONDS, json.dumps(payload))
    client.setex(STATUS_KEY.format(task_id=task_id), TTL_SECONDS, "needs_clarification")


def load_partial_state(task_id: str) -> dict[str, Any] | None:
    raw = _client().get(PARTIAL_KEY.format(task_id=task_id))
    if not raw:
        return None
    return json.loads(raw)


def get_voice_status(task_id: str) -> str | None:
    return _client().get(STATUS_KEY.format(task_id=task_id))


def delete_partial_state(task_id: str) -> None:
    client = _client()
    client.delete(PARTIAL_KEY.format(task_id=task_id))
    client.delete(STATUS_KEY.format(task_id=task_id))


def mark_queued(task_id: str) -> None:
    _client().setex(STATUS_KEY.format(task_id=task_id), TTL_SECONDS, "queued")
