from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.dependencies import get_song_service, get_style_version_service
from app.api.schemas.style_versions_api import (
    StyleVersionDetailResponse,
    StyleVersionGeneratedSongSummary,
    StyleVersionListResponse,
    StyleVersionResponse,
    style_version_to_detail,
    style_version_to_response,
)
from app.core.config import Settings, get_settings
from app.domain.enums import StyleVersionStatus
from app.services.song_service import SongService
from app.services.style_version_service import StyleVersionService


class StyleVersionStatusRequest(BaseModel):
    status: StyleVersionStatus

router = APIRouter(prefix="/api/style-versions", tags=["style-versions"])


@router.get("", response_model=StyleVersionListResponse)
def list_style_versions(style_service: StyleVersionService = Depends(get_style_version_service)):
    versions = [style_version_to_response(item) for item in style_service.list_versions()]
    return StyleVersionListResponse(style_versions=versions)


@router.get("/{version_id}", response_model=StyleVersionDetailResponse)
def get_style_version(
    version_id: str,
    style_service: StyleVersionService = Depends(get_style_version_service),
    song_service: SongService = Depends(get_song_service),
    settings: Settings = Depends(get_settings),
):
    record = style_service.get_required(version_id)
    load_path = style_service.resolve_load_path(record.id, settings.data_dir)
    songs = song_service.list_by_style_version(version_id, limit=50)
    generated = [
        StyleVersionGeneratedSongSummary(
            id=song.id,
            title=song.title,
            generation_id=song.generation_id,
            created_at=song.created_at.isoformat(),
            audio_url=song.audio_url,
        )
        for song in songs
    ]
    return style_version_to_detail(record, load_path=load_path, generated_songs=generated)


@router.patch("/{version_id}/status", response_model=StyleVersionResponse)
def update_style_version_status(
    version_id: str,
    request: StyleVersionStatusRequest,
    style_service: StyleVersionService = Depends(get_style_version_service),
):
    updated = style_service.update_status(version_id, request.status)
    return style_version_to_response(updated)

