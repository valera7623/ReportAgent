"""Admin API: users, health, celery, logs, metrics, rate limits."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.admin.auth import log_admin_action
from app.admin.dependency import admin_required
from app.admin.log_reader import LogReader
from app.admin.system_health import SystemHealth
from app.celery_app import celery_app
from app.db.admin_queries import (
    block_user_admin,
    delete_user_admin,
    get_user_detail_admin,
    list_rate_limits,
    list_users_admin,
    set_global_rate_limit,
    set_user_rate_limit,
    unblock_user_admin,
)
from app.self_healing.vector_store import force_seed_knowledge_base, get_knowledge_base
from app.utils.metrics import (
    celery_purge_total,
    get_metrics_payload,
    record_user_blocked,
    record_user_deleted,
    refresh_users_gauges,
)
from app.utils.logger import get_logger

logger = get_logger("admin_router", "log_admin.log")

router = APIRouter(prefix="/admin", tags=["Admin"])

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
CELERY_QUEUE_KEY = os.getenv("CELERY_QUEUE_NAME", "celery")
GRAFANA_DASHBOARD = (
    Path(__file__).resolve().parent.parent.parent / "grafana" / "dashboards" / "reportagent-dashboard.json"
)


# --- Models ---


class UsersListResponse(BaseModel):
    users: list[dict[str, Any]]
    total: int
    page: int
    limit: int


class BlockUserResponse(BaseModel):
    status: str
    keys_revoked: int


class UnblockUserResponse(BaseModel):
    status: str


class DeleteUserResponse(BaseModel):
    status: str
    reports_count: int
    keys_count: int


class GlobalRateLimitRequest(BaseModel):
    limit: int = Field(..., ge=1, le=10000)


class UserRateLimitRequest(BaseModel):
    limit: int = Field(..., ge=1, le=10000)


class CeleryPurgeResponse(BaseModel):
    status: str
    tasks_removed: int


class CeleryRestartResponse(BaseModel):
    status: str
    detail: str | None = None


class SeedFixesResponse(BaseModel):
    imported: int
    skipped: int


class RebuildIndexResponse(BaseModel):
    status: str
    records: int


class DeleteFixResponse(BaseModel):
    status: str


def _admin_log(request: Request, action: str, target: str | None = None, **details: Any) -> None:
    ip = getattr(request.state, "admin_ip", None)
    log_admin_action(action, target=target, details=details or None, client_ip=ip)


# --- Users ---


@router.get("/users", response_model=UsersListResponse, dependencies=[Depends(admin_required)])
async def admin_list_users(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = None,
    is_active: str = Query("all", pattern="^(true|false|all)$"),
    include_preferences: bool = False,
) -> UsersListResponse:
    users, total = list_users_admin(
        page=page,
        limit=limit,
        search=search,
        is_active=is_active,
        include_preferences=include_preferences,
    )
    _admin_log(request, "list_users", details={"page": page, "search": search})
    return UsersListResponse(users=users, total=total, page=page, limit=limit)


@router.get("/users/{user_id}", dependencies=[Depends(admin_required)])
async def admin_get_user(user_id: str, request: Request) -> dict[str, Any]:
    detail = get_user_detail_admin(user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="User not found")
    _admin_log(request, "get_user", target=user_id)
    return detail


@router.post("/users/{user_id}/block", response_model=BlockUserResponse, dependencies=[Depends(admin_required)])
async def admin_block_user(user_id: str, request: Request) -> BlockUserResponse:
    keys_revoked, found = block_user_admin(user_id)
    if not found:
        raise HTTPException(status_code=404, detail="User not found")
    record_user_blocked()
    _admin_log(request, "block_user", target=user_id, keys_revoked=keys_revoked)
    return BlockUserResponse(status="blocked", keys_revoked=keys_revoked)


@router.post("/users/{user_id}/unblock", response_model=UnblockUserResponse, dependencies=[Depends(admin_required)])
async def admin_unblock_user(user_id: str, request: Request) -> UnblockUserResponse:
    if not unblock_user_admin(user_id):
        raise HTTPException(status_code=404, detail="User not found")
    _admin_log(request, "unblock_user", target=user_id)
    return UnblockUserResponse(status="unblocked")


@router.delete("/users/{user_id}", response_model=DeleteUserResponse, dependencies=[Depends(admin_required)])
async def admin_delete_user(user_id: str, request: Request) -> DeleteUserResponse:
    result = delete_user_admin(user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="User not found")
    record_user_deleted()
    _admin_log(request, "delete_user", target=user_id, **result)
    return DeleteUserResponse(status="deleted", **result)


# --- Health ---


@router.get("/health/all", dependencies=[Depends(admin_required)])
async def admin_health_all(request: Request) -> dict[str, Any]:
    health = SystemHealth()
    result = await health.check_all()
    _admin_log(request, "health_all", details={"status": result.get("status")})
    return result


@router.get("/health/system", dependencies=[Depends(admin_required)])
async def admin_health_system(request: Request) -> dict[str, Any]:
    health = SystemHealth()
    metrics = await health.check_system_metrics()
    _admin_log(request, "health_system")
    return {"timestamp": datetime.now(timezone.utc).isoformat(), **metrics}


# --- Celery ---


@router.get("/celery/status", dependencies=[Depends(admin_required)])
async def admin_celery_status(request: Request) -> dict[str, Any]:
    client = redis.from_url(REDIS_URL, decode_responses=True)
    queue_length = int(client.llen(CELERY_QUEUE_KEY))

    workers: list[dict[str, Any]] = []
    try:
        inspect = celery_app.control.inspect(timeout=5.0)
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        stats = inspect.stats() or {}
        for name in set(list(active.keys()) + list(stats.keys())):
            workers.append(
                {
                    "name": name,
                    "active": len(active.get(name, [])),
                    "reserved": len(reserved.get(name, [])),
                    "processed": stats.get(name, {}).get("total", {}).get("tasks.reportagent.generate_report", 0)
                    if isinstance(stats.get(name), dict)
                    else 0,
                }
            )
    except Exception as exc:
        logger.warning("Celery inspect failed: %s", exc)

    queue_tasks: list[str] = []
    try:
        raw_tasks = client.lrange(CELERY_QUEUE_KEY, 0, 9)
        for raw in raw_tasks:
            try:
                body = json.loads(raw)
                queue_tasks.append(str(body.get("headers", {}).get("id", ""))[:36])
            except (json.JSONDecodeError, TypeError):
                queue_tasks.append(raw[:40])
    except Exception:
        pass

    _admin_log(request, "celery_status")
    return {
        "workers": workers,
        "queue_length": queue_length,
        "queue_tasks": queue_tasks,
    }


@router.post("/celery/purge-queue", response_model=CeleryPurgeResponse, dependencies=[Depends(admin_required)])
async def admin_celery_purge(request: Request) -> CeleryPurgeResponse:
    purged = celery_app.control.purge() or 0
    celery_purge_total.inc()
    _admin_log(request, "celery_purge", details={"tasks_removed": purged})
    return CeleryPurgeResponse(status="purged", tasks_removed=int(purged))


@router.post("/celery/restart-worker", response_model=CeleryRestartResponse, dependencies=[Depends(admin_required)])
async def admin_celery_restart(request: Request) -> CeleryRestartResponse:
    container = os.getenv("CELERY_CONTAINER_NAME", "reportagent_celery_worker")
    try:
        subprocess.Popen(
            ["docker", "restart", container],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _admin_log(request, "celery_restart", details={"container": container})
        return CeleryRestartResponse(status="restart_initiated", detail=container)
    except Exception as exc:
        _admin_log(request, "celery_restart_failed", details={"error": str(exc)})
        return CeleryRestartResponse(
            status="manual_required",
            detail=f"Run: docker restart {container}",
        )


# --- Self-healing (extended) ---


@router.get("/self-healing/stats", dependencies=[Depends(admin_required)])
async def admin_self_healing_stats(request: Request) -> dict[str, Any]:
    kb = get_knowledge_base()
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base unavailable")
    stats = kb.get_extended_stats()
    _admin_log(request, "self_healing_stats")
    return stats


@router.post("/self-healing/seed-fixes", response_model=SeedFixesResponse, dependencies=[Depends(admin_required)])
async def admin_seed_fixes(request: Request, overwrite: bool = True) -> SeedFixesResponse:
    imported, skipped = force_seed_knowledge_base(overwrite=overwrite)
    _admin_log(request, "seed_fixes", details={"imported": imported, "skipped": skipped})
    return SeedFixesResponse(imported=imported, skipped=skipped)


@router.delete("/self-healing/fixes/{fix_id}", response_model=DeleteFixResponse, dependencies=[Depends(admin_required)])
async def admin_delete_fix(fix_id: str, request: Request) -> DeleteFixResponse:
    kb = get_knowledge_base()
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base unavailable")
    if not kb.delete_fix(fix_id):
        raise HTTPException(status_code=404, detail="Fix not found")
    _admin_log(request, "delete_fix", target=fix_id)
    return DeleteFixResponse(status="deleted")


@router.post("/self-healing/rebuild-index", response_model=RebuildIndexResponse, dependencies=[Depends(admin_required)])
async def admin_rebuild_index(request: Request) -> RebuildIndexResponse:
    kb = get_knowledge_base()
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base unavailable")
    count = kb.rebuild_index()
    _admin_log(request, "rebuild_index", details={"records": count})
    return RebuildIndexResponse(status="rebuilt", records=count)


# --- Logs ---


@router.get("/logs", dependencies=[Depends(admin_required)])
async def admin_read_logs(
    request: Request,
    level: str | None = None,
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(100, ge=1, le=1000),
    search: str | None = None,
) -> dict[str, Any]:
    reader = LogReader()
    entries, total = await reader.read_logs(level=level, hours=hours, limit=limit, search=search)
    _admin_log(request, "read_logs", details={"level": level, "hours": hours})
    return {
        "logs": [
            {
                "timestamp": e.timestamp,
                "level": e.level,
                "service": e.service,
                "message": e.message,
                "source_file": e.source_file,
            }
            for e in entries
        ],
        "total": total,
        "level": level,
        "hours": hours,
    }


@router.get("/logs/download", dependencies=[Depends(admin_required)])
async def admin_download_logs(
    request: Request,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    level: str | None = None,
) -> Response:
    reader = LogReader()
    buffer = await reader.download_logs(from_date=from_date, to_date=to_date, level=level)
    _admin_log(request, "download_logs")
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=reportagent-logs.zip"},
    )


@router.get("/logs/stream", dependencies=[Depends(admin_required)])
async def admin_stream_logs(
    request: Request,
    level: str | None = None,
) -> StreamingResponse:
    reader = LogReader()

    async def event_generator():
        _admin_log(request, "stream_logs_start", details={"level": level})
        async for entry in reader.stream_logs(level=level):
            payload = json.dumps(
                {
                    "timestamp": entry.timestamp,
                    "level": entry.level,
                    "service": entry.service,
                    "message": entry.message,
                },
                ensure_ascii=False,
            )
            yield f"data: {payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- Metrics ---


@router.get("/metrics/prometheus", dependencies=[Depends(admin_required)])
async def admin_prometheus_metrics(request: Request) -> Response:
    _admin_log(request, "metrics_prometheus")
    return Response(content=get_metrics_payload(), media_type="text/plain; version=0.0.4; charset=utf-8")


@router.get("/metrics/grafana-dashboard", dependencies=[Depends(admin_required)])
async def admin_grafana_dashboard(request: Request) -> dict[str, Any]:
    if not GRAFANA_DASHBOARD.is_file():
        raise HTTPException(status_code=404, detail="Grafana dashboard JSON not found")
    _admin_log(request, "metrics_grafana_dashboard")
    return json.loads(GRAFANA_DASHBOARD.read_text(encoding="utf-8"))


@router.get("/metrics/summary", dependencies=[Depends(admin_required)])
async def admin_metrics_summary(request: Request) -> dict[str, Any]:
    from app.db.database import get_connection

    refresh_users_gauges()
    with get_connection() as conn:
        hour_row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM history
            WHERE datetime(created_at) >= datetime('now', '-1 hour')
            """
        ).fetchone()
        error_row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM history
            WHERE status = 'FAILURE'
              AND datetime(created_at) >= datetime('now', '-1 hour')
            """
        ).fetchone()
        avg_row = conn.execute(
            """
            SELECT AVG(duration_seconds) AS avg_sec FROM history
            WHERE status = 'SUCCESS'
              AND duration_seconds IS NOT NULL
              AND datetime(created_at) >= datetime('now', '-1 hour')
            """
        ).fetchone()

    client = redis.from_url(REDIS_URL, decode_responses=True)
    queue_length = int(client.llen(CELERY_QUEUE_KEY))

    _admin_log(request, "metrics_summary")
    return {
        "requests_last_hour": int(hour_row["cnt"]) if hour_row else 0,
        "errors_last_hour": int(error_row["cnt"]) if error_row else 0,
        "avg_duration_seconds": round(float(avg_row["avg_sec"]), 2) if avg_row and avg_row["avg_sec"] else 0,
        "celery_queue_length": queue_length,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# --- Rate limits ---


@router.get("/rate-limits", dependencies=[Depends(admin_required)])
async def admin_get_rate_limits(request: Request) -> dict[str, Any]:
    _admin_log(request, "get_rate_limits")
    return list_rate_limits()


@router.put("/rate-limits/global", dependencies=[Depends(admin_required)])
async def admin_set_global_rate_limit(
    body: GlobalRateLimitRequest,
    request: Request,
) -> dict[str, int]:
    limit = set_global_rate_limit(body.limit)
    _admin_log(request, "set_global_rate_limit", details={"limit": limit})
    return {"global_limit": limit}


@router.put("/rate-limits/user/{user_id}", dependencies=[Depends(admin_required)])
async def admin_set_user_rate_limit(
    user_id: str,
    body: UserRateLimitRequest,
    request: Request,
) -> dict[str, Any]:
    limit = set_user_rate_limit(user_id, body.limit)
    _admin_log(request, "set_user_rate_limit", target=user_id, details={"limit": limit})
    return {"user_id": user_id, "limit": limit}
