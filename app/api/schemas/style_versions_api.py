from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.domain.enums import StyleVersionStatus
from app.domain.style_versions import StyleVersion


class StyleVersionResponse(BaseModel):
    id: str
    name: str
    training_run_id: str
    dataset_slice_id: str
    artifact_path: str
    backend: str
    status: StyleVersionStatus
    created_at: str
    updated_at: str


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
        status=record.status,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )
