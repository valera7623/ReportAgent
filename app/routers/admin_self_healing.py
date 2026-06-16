"""Admin API for manual self-healing fix management."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.admin.dependency import admin_required
from app.self_healing.vector_store import get_knowledge_base
from app.utils.logger import get_logger

logger = get_logger("admin_self_healing", "log_self_healing.json")

router = APIRouter(prefix="/admin/self_healing", tags=["admin-self-healing"])


class AddFixRequest(BaseModel):
    error_id: str | None = Field(None, description="Optional existing error record to update")
    error_text: str = Field(..., min_length=5, description="Error text for embedding search")
    solution_prompt: str = Field("", description="LLM instructions for fix")
    solution_code: str = Field("", description="JSON action spec (no eval)")
    agent_name: str = Field(..., description="parser, analyst, visualizer, sender, intent_parser, formatter")
    error_type: str = Field("unknown", description="Error category")
    stack_trace: str = Field("", max_length=500)


class AddFixResponse(BaseModel):
    fix_id: str
    message: str


class ConfirmFixResponse(BaseModel):
    fix_id: str
    was_successful: bool
    message: str


class StatsResponse(BaseModel):
    total_fixes: int
    success_rate: float
    successful_fixes: int
    total_applications: int
    top_errors: list[dict[str, Any]]
    most_healed_agents: list[dict[str, Any]]


@router.post("/fixes", response_model=AddFixResponse, dependencies=[Depends(admin_required)])
async def add_manual_fix(body: AddFixRequest) -> AddFixResponse:
    """
    Add a manual fix candidate to the knowledge base.

    Requires **X-Admin-Key** header matching `ADMIN_API_KEY` in `.env`.
    """
    kb = get_knowledge_base()
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base unavailable")

    fix_id = body.error_id or str(uuid.uuid4())
    kb.add_error(
        {
            "id": fix_id,
            "error_text": body.error_text,
            "error_type": body.error_type,
            "agent_name": body.agent_name,
            "stack_trace": body.stack_trace,
            "solution_prompt": body.solution_prompt,
            "solution_code": body.solution_code,
            "was_successful": False,
            "success_count": 0,
            "fail_count": 0,
            "context": {"source": "manual"},
        }
    )

    from app.utils.metrics import self_healing_fixes_applied_total

    self_healing_fixes_applied_total.labels(source="manual").inc()

    logger.info("Manual fix added: %s (agent=%s)", fix_id, body.agent_name)
    return AddFixResponse(
        fix_id=fix_id,
        message="Fix added as candidate (was_successful=false). Confirm via POST /confirm/{fix_id}.",
    )


@router.post("/confirm/{fix_id}", response_model=ConfirmFixResponse, dependencies=[Depends(admin_required)])
async def confirm_fix(fix_id: str) -> ConfirmFixResponse:
    """Confirm that a fix works → sets was_successful=true."""
    kb = get_knowledge_base()
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base unavailable")

    if not kb.confirm_fix(fix_id):
        raise HTTPException(status_code=404, detail=f"Fix {fix_id} not found")

    logger.info("Fix confirmed: %s", fix_id)
    return ConfirmFixResponse(
        fix_id=fix_id,
        was_successful=True,
        message="Fix confirmed and marked as successful",
    )


@router.get("/stats", response_model=StatsResponse, dependencies=[Depends(admin_required)])
async def get_stats() -> StatsResponse:
    """Return self-healing knowledge base statistics."""
    kb = get_knowledge_base()
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base unavailable")

    stats = kb.get_stats()
    return StatsResponse(
        total_fixes=stats["total_fixes"],
        success_rate=stats["success_rate"],
        successful_fixes=stats["successful_fixes"],
        total_applications=stats["total_applications"],
        top_errors=stats["top_errors"],
        most_healed_agents=stats["most_healed_agents"],
    )
