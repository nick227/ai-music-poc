from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from app.domain.models import JobStatus
from app.domain.training import TrainingRun


class TrainingRunCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    dataset_slice_id: str
    config_preset: str = Field(default="calibration", max_length=40)


class TrainingRunResponse(BaseModel):
    id: str
    name: str
    dataset_slice_id: str
    backend: str
    base_model_version: str
    config_preset: str
    config: dict[str, Any]
    status: JobStatus
    artifact_path: Optional[str] = None
    style_version_id: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    created_at: str
    updated_at: str


class TrainingRunListResponse(BaseModel):
    runs: list[TrainingRunResponse]


class TrainingRunLogsResponse(BaseModel):
    run_id: str
    log: str


def training_run_to_response(run: TrainingRun) -> TrainingRunResponse:
    return TrainingRunResponse(
        id=run.id,
        name=run.name,
        dataset_slice_id=run.dataset_slice_id,
        backend=run.backend,
        base_model_version=run.base_model_version,
        config_preset=run.config_preset,
        config=run.config,
        status=run.status,
        artifact_path=run.artifact_path,
        style_version_id=run.style_version_id,
        error=run.error,
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        created_at=run.created_at.isoformat(),
        updated_at=run.updated_at.isoformat(),
    )
