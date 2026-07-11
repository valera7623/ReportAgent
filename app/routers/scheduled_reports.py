"""Scheduled report CRUD and Celery dispatch."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.db.database import get_connection

router = APIRouter(prefix="/api/scheduled-reports", tags=["Scheduled Reports"])


class ScheduledReportCreate(BaseModel):
    name: str = Field(default="Scheduled report", max_length=128)
    cron_expression: str = Field(default="0 9 * * 1", max_length=64)
    sheets_url: str | None = None
    email: str | None = None
    output_format: str = Field(default="pdf", max_length=32)


class ScheduledReportUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    cron_expression: str | None = Field(default=None, max_length=64)
    sheets_url: str | None = None
    email: str | None = None
    output_format: str | None = Field(default=None, max_length=32)
    enabled: bool | None = None


def _require_user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or inactive API key")
    return user_id


def _compute_next_run(cron_expression: str, *, from_dt: datetime | None = None) -> str:
    """Minimal scheduler: supports '@daily', '@weekly' or 'every_N_hours'."""
    now = from_dt or datetime.now(timezone.utc)
    expr = (cron_expression or "").strip().lower()
    if expr in ("@daily", "daily", "0 9 * * *"):
        next_dt = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    elif expr in ("@weekly", "weekly", "0 9 * * 1"):
        next_dt = now + timedelta(days=7)
    elif expr.startswith("every_") and expr.endswith("_hours"):
        try:
            hours = int(expr.replace("every_", "").replace("_hours", ""))
            next_dt = now + timedelta(hours=max(1, hours))
        except ValueError:
            next_dt = now + timedelta(days=1)
    else:
        next_dt = now + timedelta(days=1)
    return next_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "name": row["name"],
        "cron_expression": row["cron_expression"],
        "sheets_url": row["sheets_url"],
        "email": row["email"],
        "output_format": row["output_format"],
        "enabled": bool(row["enabled"]),
        "last_run_at": row["last_run_at"],
        "next_run_at": row["next_run_at"],
        "created_at": row["created_at"],
    }


@router.get("")
async def list_scheduled_reports(request: Request) -> dict[str, Any]:
    user_id = _require_user_id(request)
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM scheduled_reports WHERE user_id = ? ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return {"schedules": [_row_to_dict(r) for r in rows]}


@router.post("", status_code=201)
async def create_scheduled_report(request: Request, body: ScheduledReportCreate) -> dict[str, Any]:
    user_id = _require_user_id(request)
    if not body.sheets_url:
        raise HTTPException(status_code=400, detail="sheets_url is required for scheduled reports")
    schedule_id = str(uuid.uuid4())
    next_run = _compute_next_run(body.cron_expression)
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO scheduled_reports
                (id, user_id, name, cron_expression, sheets_url, email, output_format, enabled, next_run_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            """,
            (
                schedule_id,
                user_id,
                body.name,
                body.cron_expression,
                body.sheets_url,
                body.email,
                body.output_format,
                next_run,
            ),
        )
        row = conn.execute(
            "SELECT * FROM scheduled_reports WHERE id = ?",
            (schedule_id,),
        ).fetchone()
    return _row_to_dict(row)


@router.patch("/{schedule_id}")
async def update_scheduled_report(
    request: Request,
    schedule_id: str,
    body: ScheduledReportUpdate,
) -> dict[str, Any]:
    user_id = _require_user_id(request)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM scheduled_reports WHERE id = ? AND user_id = ?",
            (schedule_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Schedule not found")

        updates: dict[str, Any] = {}
        for field in ("name", "cron_expression", "sheets_url", "email", "output_format"):
            val = getattr(body, field)
            if val is not None:
                updates[field] = val
        if body.enabled is not None:
            updates["enabled"] = 1 if body.enabled else 0
        if body.cron_expression is not None:
            updates["next_run_at"] = _compute_next_run(body.cron_expression)

        if updates:
            sets = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE scheduled_reports SET {sets} WHERE id = ? AND user_id = ?",
                (*updates.values(), schedule_id, user_id),
            )
        row = conn.execute(
            "SELECT * FROM scheduled_reports WHERE id = ?",
            (schedule_id,),
        ).fetchone()
    return _row_to_dict(row)


@router.delete("/{schedule_id}", status_code=204)
async def delete_scheduled_report(request: Request, schedule_id: str) -> None:
    user_id = _require_user_id(request)
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM scheduled_reports WHERE id = ? AND user_id = ?",
            (schedule_id, user_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Schedule not found")
