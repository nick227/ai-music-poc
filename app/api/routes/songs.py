from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_job_service, get_media_store
from app.core.errors import NotFoundError
from app.core.job_paths import stable_output_path
from app.domain.models import (
    JobRecord,
    MediaAsset,
    MediaKind,
    SongGenerationSummary,
    SongListResponse,
    SongResponse,
)
from app.services.job_service import JobService
from app.storage.local_media_store import LocalMediaStore

router = APIRouter(prefix="/api", tags=["songs"])


def _generation_summary(job: JobRecord | None) -> SongGenerationSummary | None:
    if job is None:
        return None
    version_details = job.version_details or {}
    return SongGenerationSummary(
        id=job.id,
        status=job.status,
        output_path=stable_output_path(job),
        prompt=job.request.prompt,
        lyrics=job.request.lyrics,
        seed=job.request.seed,
        backend=version_details.get("backend"),
        model_version=version_details.get("modelVersion"),
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


def _song_response(asset: MediaAsset, job_service: JobService) -> SongResponse:
    job: JobRecord | None = None
    if asset.generation_id:
        job = job_service.get(asset.generation_id)
    return SongResponse(
        id=asset.id,
        title=asset.title,
        media_asset_id=asset.id,
        kind=asset.kind,
        file_path=asset.file_path,
        duration_seconds=asset.duration_seconds,
        sample_rate=asset.sample_rate,
        channels=asset.channels,
        review_status=asset.review_status,
        generation_id=asset.generation_id,
        version_details=asset.version_details,
        generation=_generation_summary(job),
        created_at=asset.created_at,
        updated_at=asset.updated_at,
    )


@router.get("/songs", response_model=SongListResponse)
def list_songs(
    limit: int = Query(default=25, ge=1, le=100),
    media_store: LocalMediaStore = Depends(get_media_store),
    job_service: JobService = Depends(get_job_service),
):
    songs = [
        _song_response(asset, job_service)
        for asset in media_store.list_generated_songs(limit=limit)
    ]
    return SongListResponse(songs=songs)


@router.get("/songs/{song_id}", response_model=SongResponse)
def get_song(
    song_id: str,
    media_store: LocalMediaStore = Depends(get_media_store),
    job_service: JobService = Depends(get_job_service),
):
    asset = media_store.get(song_id)
    if asset is None or asset.kind != MediaKind.GENERATED_SONG:
        raise NotFoundError("Song not found")
    return _song_response(asset, job_service)
