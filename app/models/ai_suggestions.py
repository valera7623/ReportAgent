"""Pydantic models for AI report suggestions."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ColumnTypes(BaseModel):
    date: str | None = None
    numeric: list[str] = Field(default_factory=list)
    category: list[str] = Field(default_factory=list)
    text: list[str] = Field(default_factory=list)


class SuggestedChart(BaseModel):
    type: str
    x: str
    y: str | None = None
    title: str = ""


class AISuggestionsPayload(BaseModel):
    columns: ColumnTypes = Field(default_factory=ColumnTypes)
    suggested_charts: list[SuggestedChart] = Field(default_factory=list)
    description: str = ""
    insights: list[str] = Field(default_factory=list)
    aggregations: dict[str, list[str]] = Field(default_factory=dict)
    file_hash: str | None = None
    source: str = "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class AnalyzeResponse(AISuggestionsPayload):
    cached: bool = False
    ai_enabled: bool = True


class GenerateWithAIRequest(BaseModel):
    email: str | None = None
    output_format: str | None = None
    accept_suggestions: bool = True
    chart_overrides: list[SuggestedChart] | None = None


class AISuggestionRecord(BaseModel):
    id: int
    user_id: str
    file_hash: str
    suggestions: dict[str, Any]
    created_at: datetime
    expires_at: datetime
