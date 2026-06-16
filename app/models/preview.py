"""Pydantic models for report preview API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, EmailStr, Field


class PreviewChart(BaseModel):
    type: str
    title: str
    image_url: str
    index: int = 0
    column: str | None = None


class PreviewColumn(BaseModel):
    name: str
    type: str
    sample: Any = None


class PreviewData(BaseModel):
    headers: list[str]
    rows: list[list[Any]]
    total_rows: int
    summary: dict[str, Any]
    charts: list[PreviewChart]
    suggested_chart_types: list[str]
    columns: list[PreviewColumn]


class PreviewResponse(BaseModel):
    preview_id: str
    status: str = "ready"
    data: PreviewData | None = None
    expires_at: str
    message: str | None = None


class PreviewConfirmRequest(BaseModel):
    preview_id: str
    email: EmailStr | None = None
    output_format: str | None = Field(default="pdf")


class PreviewConfirmResponse(BaseModel):
    task_id: str
    download_url: str
    output_format: str
    message: str


class RegenerateChartRequest(BaseModel):
    preview_id: str
    chart_index: int = Field(ge=0)
    chart_type: str = Field(pattern="^(bar|line|pie)$")


class RegenerateChartResponse(BaseModel):
    image_url: str
    chart: PreviewChart
