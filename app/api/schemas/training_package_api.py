from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.api.schemas.training_api import TrainingRunResponse, TrainingPipelineStatusResponse, training_run_to_response
from app.domain.slices import DatasetSlice
from app.domain.training import TrainingRun
from app.domain.training_status import describe_package


class ReadyAudioItem(BaseModel):
    id: str
    title: str
    duration_seconds: Optional[float] = None
    category_count: int
    concept_count: int
    concept_ids: list[str]
    category_ids: list[str]
    primary_role: Optional[str] = None
    quality_score: Optional[int] = None
    fit_score: Optional[int] = None
    ingestion_status: str
    updated_at: str
    group_label: str


class ReadyAudioGroup(BaseModel):
    label: str
    concept_id: Optional[str] = None
    items: list[ReadyAudioItem]


class ReadyAudioResponse(BaseModel):
    concept_id: Optional[str] = None
    total: int
    groups: list[ReadyAudioGroup]
    items: list[ReadyAudioItem]


class TrainingPackageResponse(BaseModel):
    id: str
    name: str
    track_count: int
    status: str
    status_label: str
    download_ready: bool
    created_at: str
    updated_at: str
    download_url: str


class TrainingPackageListResponse(BaseModel):
    packages: list[TrainingPackageResponse]


class CreatePackageRequest(BaseModel):
    concept_id: Optional[str] = None
    media_ids: list[str] = Field(default_factory=list)
    name: Optional[str] = Field(default=None, max_length=160)
    start_training: bool = True
    config_preset: str = Field(default="calibration", max_length=40)
    confirm_real_training: bool = False


class CreatePackageResponse(BaseModel):
    package: TrainingPackageResponse
    run: Optional[TrainingRunResponse] = None


def package_to_response(record: DatasetSlice) -> TrainingPackageResponse:
    package_status = describe_package(record)
    return TrainingPackageResponse(
        id=record.id,
        name=record.name,
        track_count=record.asset_count,
        status=record.status.value,
        status_label=package_status["status_label"],
        download_ready=package_status["download_ready"],
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
        download_url=f"/api/slices/{record.id}/package",
    )


def create_package_response(record: DatasetSlice, run: TrainingRun | None, settings=None) -> CreatePackageResponse:
    return CreatePackageResponse(
        package=package_to_response(record),
        run=training_run_to_response(run, settings) if run else None,
    )
