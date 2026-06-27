from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.domain.models import JobStatus


class TrainingRun(BaseModel):
    id: str = Field(default_factory=lambda: f"train_{uuid4().hex}")
    name: str
    dataset_slice_id: str
    backend: str = "MOCK"
    base_model_version: str = "mock-v1"
    config_preset: str
    config: dict[str, Any] = Field(default_factory=dict)
    status: JobStatus = JobStatus.QUEUED
    artifact_path: Optional[str] = None
    style_version_id: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be empty")
        return value
