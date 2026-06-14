"""Prometheus metrics initialization and agent tracking decorators."""

from __future__ import annotations

import functools
import hashlib
import os
import threading
import time
from typing import Any, Callable, TypeVar

import redis
from prometheus_client import Counter, Gauge, Histogram, generate_latest

from app.db.database import count_active_users, resolve_db_path
from app.utils.logger import get_logger, log_metric_event

logger = get_logger("metrics", "log_api.log")

F = TypeVar("F", bound=Callable[..., Any])

AGENT_DURATION_BUCKETS = (0.1, 0.5, 1, 2, 5, 10, 30, 60)
REPORT_DURATION_BUCKETS = (1, 5, 10, 30, 60, 120, 300, 600)

report_requests_total = Counter(
    "report_requests_total",
    "Total HTTP requests to the API",
    ["endpoint", "status", "user_id_hash"],
)

agent_errors_total = Counter(
    "agent_errors_total",
    "Total agent execution errors",
    ["agent_name", "error_type"],
)

agent_duration_seconds = Histogram(
    "agent_duration_seconds",
    "Agent execution duration in seconds",
    ["agent_name"],
    buckets=AGENT_DURATION_BUCKETS,
)

report_generation_duration_seconds = Histogram(
    "report_generation_duration_seconds",
    "End-to-end report generation duration in seconds",
    ["source_type"],
    buckets=REPORT_DURATION_BUCKETS,
)

celery_queue_length = Gauge(
    "celery_queue_length",
    "Number of tasks waiting in the Celery queue",
)

voice_transcriptions_total = Counter(
    "voice_transcriptions_total",
    "Voice transcription attempts",
    ["status"],
)

active_users = Gauge(
    "active_users",
    "Number of active users (used API in last 30 days)",
)

database_size_bytes = Gauge(
    "database_size_bytes",
    "SQLite users.db file size in bytes",
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["endpoint", "method"],
    buckets=AGENT_DURATION_BUCKETS,
)

report_format_requests_total = Counter(
    "report_format_requests_total",
    "Report formatting requests by output format",
    ["output_format", "status"],
)

report_format_duration_seconds = Histogram(
    "report_format_duration_seconds",
    "Report formatting duration in seconds",
    ["output_format"],
    buckets=AGENT_DURATION_BUCKETS,
)

notion_api_errors_total = Counter(
    "notion_api_errors_total",
    "Notion API errors during report export",
)

google_slides_api_errors_total = Counter(
    "google_slides_api_errors_total",
    "Google Slides API errors during report export",
)

_background_started = False
_background_lock = threading.Lock()
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CELERY_QUEUE_KEY = os.getenv("CELERY_QUEUE_NAME", "celery")
METRICS_QUEUE_REDIS_KEY = "metrics:celery_queue_length"


def hash_user_id(user_id: str | None) -> str:
    """Return first 8 chars of MD5 hash for GDPR-safe labeling."""
    if not user_id:
        return "anon"
    return hashlib.md5(user_id.encode("utf-8")).hexdigest()[:8]


def _redis_client() -> redis.Redis:
    return redis.from_url(REDIS_URL, decode_responses=True)


def refresh_celery_queue_length() -> None:
    """Read queue length from Redis (written by Celery beat or live llen)."""
    try:
        client = _redis_client()
        cached = client.get(METRICS_QUEUE_REDIS_KEY)
        if cached is not None:
            celery_queue_length.set(int(cached))
            return
        celery_queue_length.set(int(client.llen(CELERY_QUEUE_KEY)))
    except Exception as exc:
        logger.warning("Failed to refresh celery_queue_length: %s", exc)


def refresh_active_users() -> None:
    """Update active_users gauge from SQLite."""
    try:
        active_users.set(count_active_users())
    except Exception as exc:
        logger.warning("Failed to refresh active_users: %s", exc)


def refresh_database_size() -> None:
    """Update database_size_bytes gauge from filesystem."""
    try:
        db_path = resolve_db_path()
        if db_path.is_file():
            database_size_bytes.set(db_path.stat().st_size)
        else:
            database_size_bytes.set(0)
    except Exception as exc:
        logger.warning("Failed to refresh database_size_bytes: %s", exc)


def refresh_all_gauges() -> None:
    """Refresh all gauges (called on /metrics scrape)."""
    refresh_celery_queue_length()
    refresh_active_users()
    refresh_database_size()


def _background_loop(interval: float, func: Callable[[], None], name: str) -> None:
    while True:
        try:
            func()
        except Exception as exc:
            logger.warning("Background gauge updater %s failed: %s", name, exc)
        time.sleep(interval)


def start_background_gauge_updaters() -> None:
    """Start background threads for heavy gauge updates (non-blocking for agents)."""
    global _background_started
    with _background_lock:
        if _background_started:
            return
        _background_started = True

    threading.Thread(
        target=_background_loop,
        args=(30.0, refresh_celery_queue_length, "celery_queue"),
        daemon=True,
        name="metrics-celery-queue",
    ).start()

    threading.Thread(
        target=_background_loop,
        args=(300.0, refresh_active_users, "active_users"),
        daemon=True,
        name="metrics-active-users",
    ).start()

    threading.Thread(
        target=_background_loop,
        args=(300.0, refresh_database_size, "database_size"),
        daemon=True,
        name="metrics-database-size",
    ).start()

    logger.info("Started background Prometheus gauge updaters")


def get_metrics_payload() -> bytes:
    """Return latest Prometheus metrics exposition format."""
    refresh_all_gauges()
    return generate_latest()


def record_format_request(
    output_format: str,
    status: str,
    duration_seconds: float | None = None,
) -> None:
    """Increment format counter and optionally observe duration."""
    report_format_requests_total.labels(
        output_format=output_format,
        status=status,
    ).inc()
    if duration_seconds is not None and status != "cached":
        report_format_duration_seconds.labels(output_format=output_format).observe(
            duration_seconds
        )
    log_metric_event(
        "report_format",
        {
            "output_format": output_format,
            "status": status,
            "duration_seconds": round(duration_seconds, 4) if duration_seconds else None,
        },
    )


def record_voice_transcription(success: bool) -> None:
    """Increment voice transcription counter."""
    status = "success" if success else "fail"
    voice_transcriptions_total.labels(status=status).inc()
    log_metric_event(
        "voice_transcription",
        {"status": status},
    )


def track_agent_metrics(agent_name: str) -> Callable[[F], F]:
    """Decorator: measure agent duration, count errors, log structured metric event."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration = time.perf_counter() - start
                agent_duration_seconds.labels(agent_name=agent_name).observe(duration)
                log_metric_event(
                    "agent_success",
                    {
                        "agent_name": agent_name,
                        "duration_seconds": round(duration, 4),
                    },
                )
                return result
            except Exception as exc:
                duration = time.perf_counter() - start
                error_type = type(exc).__name__
                agent_errors_total.labels(
                    agent_name=agent_name,
                    error_type=error_type,
                ).inc()
                agent_duration_seconds.labels(agent_name=agent_name).observe(duration)
                log_metric_event(
                    "agent_error",
                    {
                        "agent_name": agent_name,
                        "error_type": error_type,
                        "duration_seconds": round(duration, 4),
                    },
                )
                raise

        return wrapper  # type: ignore[return-value]

    return decorator
