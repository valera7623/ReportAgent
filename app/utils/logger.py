"""Centralized logging: stdout + per-agent log files in ./logs/."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_DIR = Path(os.getenv("LOG_DIR", "/app/logs"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"

_configured: set[str] = set()
_metrics_logger = logging.getLogger("metrics_json")


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_logger(name: str, log_file: str | None = None) -> logging.Logger:
    """
    Return a logger that writes to stdout and optionally to a dedicated file.

    Agent log files: log_parser.log, log_analyst.log, log_visualizer.log, log_sender.log
    """
    logger = logging.getLogger(name)

    if name in _configured:
        return logger

    logger.setLevel(LOG_LEVEL)
    logger.propagate = False

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FMT)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if log_file:
        _ensure_log_dir()
        file_path = LOG_DIR / log_file
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _configured.add(name)
    return logger


def _ensure_metrics_logger() -> logging.Logger:
    if _metrics_logger.handlers:
        return _metrics_logger
    _metrics_logger.setLevel(LOG_LEVEL)
    _metrics_logger.propagate = False
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _metrics_logger.addHandler(handler)
    return _metrics_logger


def log_metric_event(event: str, fields: dict[str, Any]) -> None:
    """Emit structured JSON metric events to stdout (for log aggregation)."""
    payload = {
        "type": "metric",
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    _ensure_metrics_logger().info(json.dumps(payload, ensure_ascii=False))
