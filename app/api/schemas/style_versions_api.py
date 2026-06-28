from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.domain.enums import StyleVersionStatus
from app.domain.models import SongResponse
from app.domain.style_versions import StyleVersion


class StyleVersionResponse(BaseModel):
    id: str
    name: str
    training_run_id: str
    dataset_slice_id: str
    artifact_path: str
    backend: str
    base_model_id: str
    base_model_name: str
    training_mode: str
    artifact_type: str
    status: StyleVersionStatus
    created_at: str
    updated_at: str


class StyleVersionGeneratedSongSummary(BaseModel):
    id: str
    title: str
    generation_id: Optional[str] = None
    created_at: str
    audio_url: Optional[str] = None


class StyleVersionDetailResponse(StyleVersionResponse):
    load_path: str
    generated_songs: list[StyleVersionGeneratedSongSummary]


class StyleVersionListResponse(BaseModel):
    style_versions: list[StyleVersionResponse]


def style_version_to_response(record: StyleVersion) -> StyleVersionResponse:
    return StyleVersionResponse(
        id=record.id,
        name=record.name,
        training_run_id=record.training_run_id,
        dataset_slice_id=record.dataset_slice_id,
        artifact_path=record.artifact_path,
        backend=record.backend,
        base_model_id=record.base_model_id,
        base_model_name=record.base_model_name,
        training_mode=record.training_mode,
        artifact_type=record.artifact_type,
        status=record.status,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


def style_version_to_detail(
    record: StyleVersion,
    *,
    load_path: str,
    generated_songs: list[StyleVersionGeneratedSongSummary],
) -> StyleVersionDetailResponse:
    base = style_version_to_response(record)
    return StyleVersionDetailResponse(
        **base.model_dump(),
        load_path=load_path,
        generated_songs=generated_songs,
    )
