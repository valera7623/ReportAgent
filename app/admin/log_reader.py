"""Async log file reader for admin API."""

from __future__ import annotations

import asyncio
import io
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator

from app.utils.logger import LOG_DIR, get_logger

logger = get_logger("log_reader", "log_admin.log")

LOG_LINE_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ \| (\w+)\s+\| ([^|]+) \| (.*)$"
)

DEFAULT_LOG_FILES = (
    "log_api.log",
    "log_parser.log",
    "log_analyst.log",
    "log_visualizer.log",
    "log_formatter.log",
    "log_sender.log",
    "log_tasks.log",
    "log_voice.log",
    "log_context_loader.log",
    "log_webhook.log",
    "log_self_healing.json",
    "log_admin.log",
)


@dataclass
class LogEntry:
    timestamp: str
    level: str
    service: str
    message: str
    source_file: str


def _allowed_levels() -> set[str]:
    raw = os.getenv("ADMIN_LOGS_ALLOWED_LEVELS", "ERROR,WARNING,INFO")
    return {lvl.strip().upper() for lvl in raw.split(",") if lvl.strip()}


def _max_lines() -> int:
    return int(os.getenv("ADMIN_LOGS_MAX_LINES", "1000"))


def _parse_line(line: str, source: str) -> LogEntry | None:
    line = line.strip()
    if not line:
        return None
    match = LOG_LINE_RE.match(line)
    if match:
        ts, level, service, message = match.groups()
        return LogEntry(
            timestamp=ts,
            level=level.upper(),
            service=service.strip(),
            message=message.strip(),
            source_file=source,
        )
    if source.endswith(".json") and line.startswith("{"):
        return LogEntry(
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            level="INFO",
            service="json",
            message=line[:500],
            source_file=source,
        )
    return LogEntry(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        level="INFO",
        service=source,
        message=line[:500],
        source_file=source,
    )


def _parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class LogReader:
    """Read and filter application log files."""

    def __init__(self, log_dir: Path | None = None) -> None:
        self.log_dir = log_dir or LOG_DIR

    def _iter_log_files(self) -> list[Path]:
        if not self.log_dir.is_dir():
            return []
        files = list(self.log_dir.glob("log_*.log")) + list(self.log_dir.glob("log_*.json"))
        if not files:
            return [self.log_dir / name for name in DEFAULT_LOG_FILES if (self.log_dir / name).is_file()]
        return sorted(files)

    async def read_logs(
        self,
        *,
        level: str | None = None,
        hours: int = 24,
        limit: int = 100,
        search: str | None = None,
    ) -> tuple[list[LogEntry], int]:
        limit = min(limit, _max_lines())
        level_filter = level.upper() if level else None
        allowed = _allowed_levels()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, hours))
        search_lower = search.lower() if search else None

        entries: list[LogEntry] = []

        for path in self._iter_log_files():
            if not path.is_file():
                continue
            try:
                content = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.warning("Cannot read %s: %s", path, exc)
                continue

            for line in content.splitlines():
                entry = _parse_line(line, path.name)
                if entry is None:
                    continue
                if entry.level not in allowed:
                    continue
                if level_filter and entry.level != level_filter:
                    continue
                ts = _parse_ts(entry.timestamp)
                if ts and ts < cutoff:
                    continue
                if search_lower and search_lower not in entry.message.lower():
                    continue
                entries.append(entry)

        entries.sort(key=lambda e: e.timestamp, reverse=True)
        total = len(entries)
        return entries[:limit], total

    async def download_logs(
        self,
        *,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        level: str | None = None,
    ) -> io.BytesIO:
        to_dt = to_date or datetime.now(timezone.utc)
        from_dt = from_date or (to_dt - timedelta(days=1))
        level_filter = level.upper() if level else None

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in self._iter_log_files():
                if not path.is_file():
                    continue
                try:
                    content = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")
                except OSError:
                    continue

                filtered_lines: list[str] = []
                for line in content.splitlines():
                    entry = _parse_line(line, path.name)
                    if entry is None:
                        continue
                    if level_filter and entry.level != level_filter:
                        continue
                    ts = _parse_ts(entry.timestamp)
                    if ts and (ts < from_dt or ts > to_dt):
                        continue
                    filtered_lines.append(line)

                if filtered_lines:
                    zf.writestr(path.name, "\n".join(filtered_lines))

        buffer.seek(0)
        return buffer

    async def stream_logs(
        self,
        *,
        level: str | None = None,
        poll_interval: float = 1.0,
    ) -> AsyncIterator[LogEntry]:
        """Yield new log lines (tail -f style) for SSE."""
        level_filter = level.upper() if level else None
        positions: dict[str, int] = {}

        while True:
            for path in self._iter_log_files():
                if not path.is_file():
                    continue
                try:
                    size = path.stat().st_size
                    pos = positions.get(str(path), size)
                    if size < pos:
                        pos = 0
                    if size == pos:
                        continue
                    with path.open("r", encoding="utf-8", errors="replace") as fh:
                        fh.seek(pos)
                        new_data = fh.read()
                        positions[str(path)] = fh.tell()
                except OSError:
                    continue

                for line in new_data.splitlines():
                    entry = _parse_line(line, path.name)
                    if entry is None:
                        continue
                    if level_filter and entry.level != level_filter:
                        continue
                    yield entry

            await asyncio.sleep(poll_interval)
