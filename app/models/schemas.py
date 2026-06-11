"""Pydantic models for API requests and responses."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, EmailStr, Field, model_validator


class ReportRequest(BaseModel):
    """JSON body fields (file is uploaded separately as multipart)."""

    email: EmailStr | None = Field(
        default=None,
        description="Optional recipient email. Omit to download PDF via API only.",
    )
    sheets_url: str | None = Field(
        default=None,
        description="Public Google Sheets URL",
        examples=["https://docs.google.com/spreadsheets/d/abc123/edit"],
    )

    @model_validator(mode="after")
    def validate_source(self) -> ReportRequest:
        if self.sheets_url is not None:
            url = self.sheets_url.strip()
            if not url:
                raise ValueError("sheets_url cannot be empty when provided")
            self.sheets_url = url
        return self


class TaskState(str, Enum):
    PENDING = "PENDING"
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    RETRY = "RETRY"
    REVOKED = "REVOKED"


class GenerateReportResponse(BaseModel):
    task_id: str
    status: str = "queued"
    message: str
    download_url: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskState
    result: dict[str, Any] | None = None
    error: str | None = None


class AgentError(Exception):
    """Human-readable error raised by agents."""

    def __init__(self, message: str, agent: str = "unknown") -> None:
        self.message = message
        self.agent = agent
        super().__init__(message)
