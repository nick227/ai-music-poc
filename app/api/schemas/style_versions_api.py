from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.domain.enums import StyleVersionStatus
from app.domain.models import SongResponse
from app.domain.style_versions import StyleVersion


class StyleVersionResponse(BaseModel):
    id: str
    name: str
    type: str = "LoRA"
    training_run_id: str
    dataset_id: str
    dataset_slice_id: str
    lora_path: str
    artifact_path: str
    backend: str
    base_model_id: str
    base_model_name: str
    training_mode: str
    artifact_type: str
    status: StyleVersionStatus
    ace_loadable: bool = False
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


def style_version_to_response(record: StyleVersion, *, ace_loadable: bool = False) -> StyleVersionResponse:
    return StyleVersionResponse(
        id=record.id,
        name=record.name,
        type="LoRA" if record.artifact_type in {"lora", "lora_adapter", "adapter", "adapter_dir"} else record.artifact_type,
        training_run_id=record.training_run_id,
        dataset_id=record.dataset_slice_id,
        dataset_slice_id=record.dataset_slice_id,
        lora_path=record.artifact_path,
        artifact_path=record.artifact_path,
        backend=record.backend,
        base_model_id=record.base_model_id,
        base_model_name=record.base_model_name,
        training_mode=record.training_mode,
        artifact_type=record.artifact_type,
        status=record.status,
        ace_loadable=ace_loadable,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


def style_version_to_detail(
    record: StyleVersion,
    *,
    load_path: str,
    generated_songs: list[StyleVersionGeneratedSongSummary],
    ace_loadable: bool = False,
) -> StyleVersionDetailResponse:
    base = style_version_to_response(record, ace_loadable=ace_loadable)
    payload = base.model_dump()
    payload["lora_path"] = load_path
    return StyleVersionDetailResponse(
        **payload,
        load_path=load_path,
        generated_songs=generated_songs,
    )
