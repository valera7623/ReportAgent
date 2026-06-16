"""Parallel system health checks with short-lived cache."""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import redis

from app.celery_app import celery_app
from app.db.database import get_connection
from app.self_healing.config import is_self_healing_enabled
from app.utils.logger import get_logger

logger = get_logger("system_health", "log_admin.log")

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
STORAGE_DIR = Path(os.getenv("PDF_DIR", "/app/storage/pdfs")).parent
CACHE_TTL_SECONDS = 10

_cache: dict[str, Any] = {}
_cache_ts: float = 0.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _timed(coro) -> tuple[Any, float]:
    start = time.perf_counter()
    try:
        result = await coro
        ms = round((time.perf_counter() - start) * 1000, 1)
        return result, ms
    except Exception as exc:
        ms = round((time.perf_counter() - start) * 1000, 1)
        return {"status": "down", "error": str(exc)}, ms


class SystemHealth:
    """Check infrastructure dependencies."""

    async def check_db(self) -> dict[str, Any]:
        def _ping():
            with get_connection() as conn:
                conn.execute("SELECT 1").fetchone()
            return {"status": "ok"}

        result, ms = await _timed(asyncio.to_thread(_ping))
        if isinstance(result, dict) and result.get("status") == "ok":
            result["latency_ms"] = ms
        return result if isinstance(result, dict) else {"status": "down", "latency_ms": ms}

    async def check_redis(self) -> dict[str, Any]:
        def _ping():
            client = redis.from_url(REDIS_URL, decode_responses=True)
            client.ping()
            return {"status": "ok"}

        result, ms = await _timed(asyncio.to_thread(_ping))
        if isinstance(result, dict) and result.get("status") == "ok":
            result["latency_ms"] = ms
        return result if isinstance(result, dict) else {"status": "down", "latency_ms": ms}

    async def check_celery(self) -> dict[str, Any]:
        def _ping():
            replies = celery_app.control.ping(timeout=5.0)
            workers = []
            for reply in replies or []:
                for name, info in reply.items():
                    workers.append(
                        {
                            "name": name,
                            "active": info.get("active", 0) if isinstance(info, dict) else 0,
                        }
                    )
            return {
                "status": "ok" if workers else "degraded",
                "workers": len(workers),
                "worker_names": [w["name"] for w in workers],
            }

        result, ms = await _timed(asyncio.to_thread(_ping))
        if isinstance(result, dict):
            result["latency_ms"] = ms
        return result if isinstance(result, dict) else {"status": "down", "latency_ms": ms}

    async def check_chromadb(self) -> dict[str, Any]:
        if not is_self_healing_enabled():
            return {"status": "disabled", "records": 0}

        def _check():
            from app.self_healing.vector_store import get_knowledge_base

            kb = get_knowledge_base()
            if kb is None:
                return {"status": "down", "records": 0}
            stats = kb.get_stats()
            return {"status": "ok", "records": stats.get("total_fixes", 0)}

        result, ms = await _timed(asyncio.to_thread(_check))
        if isinstance(result, dict):
            result["latency_ms"] = ms
        return result if isinstance(result, dict) else {"status": "down", "latency_ms": ms}

    async def check_openai(self) -> dict[str, Any]:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return {"status": "disabled"}

        def _check():
            import httpx

            base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(
                    f"{base}/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )
            if resp.status_code == 200:
                return {"status": "ok"}
            return {"status": "degraded", "http_status": resp.status_code}

        result, ms = await _timed(asyncio.to_thread(_check))
        if isinstance(result, dict):
            result["latency_ms"] = ms
        return result if isinstance(result, dict) else {"status": "down", "latency_ms": ms}

    async def check_disk(self) -> dict[str, Any]:
        def _check():
            path = STORAGE_DIR if STORAGE_DIR.exists() else Path("/")
            usage = shutil.disk_usage(path)
            free_gb = round(usage.free / (1024**3), 2)
            used_percent = round((usage.used / usage.total) * 100, 1) if usage.total else 0
            status = "ok" if free_gb > 1.0 else "degraded"
            return {
                "status": status,
                "free_gb": free_gb,
                "used_percent": used_percent,
                "free_bytes": usage.free,
                "path": str(path),
            }

        result, _ = await _timed(asyncio.to_thread(_check))
        return result if isinstance(result, dict) else {"status": "down"}

    async def check_all(self) -> dict[str, Any]:
        global _cache, _cache_ts
        now = time.time()
        if _cache and (now - _cache_ts) < CACHE_TTL_SECONDS:
            return _cache

        db, redis_r, celery_r, chroma, openai_r, disk = await asyncio.gather(
            self.check_db(),
            self.check_redis(),
            self.check_celery(),
            self.check_chromadb(),
            self.check_openai(),
            self.check_disk(),
        )

        services = {
            "db": db,
            "redis": redis_r,
            "celery": celery_r,
            "chromadb": chroma,
            "openai": openai_r,
            "disk": disk,
        }

        statuses = [s.get("status", "down") for s in services.values()]
        if all(s in ("ok", "disabled") for s in statuses):
            overall = "ok"
        elif any(s == "down" for s in statuses):
            overall = "down"
        else:
            overall = "degraded"

        payload = {
            "status": overall,
            "services": services,
            "timestamp": _now_iso(),
        }
        _cache = payload
        _cache_ts = now
        return payload

    async def check_system_metrics(self) -> dict[str, Any]:
        def _metrics():
            try:
                import psutil

                vm = psutil.virtual_memory()
                disk = psutil.disk_usage("/")
                net = psutil.net_io_counters()
                load = os.getloadavg() if hasattr(os, "getloadavg") else (0, 0, 0)
                return {
                    "cpu": {
                        "percent": psutil.cpu_percent(interval=0.1),
                        "load_avg": list(load),
                    },
                    "ram": {
                        "total_bytes": vm.total,
                        "used_bytes": vm.used,
                        "percent": vm.percent,
                    },
                    "disk": {
                        "total_bytes": disk.total,
                        "used_bytes": disk.used,
                        "free_bytes": disk.free,
                        "percent": disk.percent,
                    },
                    "network": {
                        "rx_bytes": net.bytes_recv,
                        "tx_bytes": net.bytes_sent,
                    },
                }
            except ImportError:
                return {
                    "cpu": {"percent": None, "load_avg": []},
                    "ram": {"total_bytes": None, "used_bytes": None, "percent": None},
                    "disk": {"total_bytes": None, "used_bytes": None, "free_bytes": None},
                    "network": {"rx_bytes": None, "tx_bytes": None},
                    "note": "Install psutil for host metrics",
                }

        return await asyncio.to_thread(_metrics)
