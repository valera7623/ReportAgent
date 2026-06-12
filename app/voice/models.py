"""Pydantic models for voice endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class IntentData(BaseModel):
    source_type: str | None = None
    source_value: str | None = None
    chart_type: str | None = None
    metrics: list[str] = Field(default_factory=list)
    group_by: str | None = None
    target_email: str | None = None
    missing_info: list[str] = Field(default_factory=list)
    raw_transcript: str | None = None


class VoiceGenerateReportResponse(BaseModel):
    task_id: str
    status: Literal["queued", "needs_clarification", "processing"]
    message: str
    transcript: str | None = None
    intent: dict[str, Any] | None = None
    clarification_question: str | None = None
    partial_intent: dict[str, Any] | None = None
    download_url: str | None = None
    user_id: str | None = None
    usage_count: int = 0


class VoiceClarifyRequest(BaseModel):
    task_id: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1, description="User clarification text")


class VoiceClarifyResponse(BaseModel):
    task_id: str
    status: Literal["queued", "needs_clarification"]
    message: str
    clarification_question: str | None = None
    partial_intent: dict[str, Any] | None = None
    download_url: str | None = None
