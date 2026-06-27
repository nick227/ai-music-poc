from typing import List

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse

from app.api.dependencies import get_media_service
from app.api.schemas.taxonomy_api import MediaAssignmentsRequest, MediaDetailResponse, MediaImportResponse, MediaListResponse
from app.domain.models import MediaKind, ReviewStatus
from app.services.media_service import MediaService

router = APIRouter(prefix="/api/media", tags=["media"])


def _detail(asset_payload: dict) -> MediaDetailResponse:
    return MediaDetailResponse(
        id=asset_payload["id"],
        title=asset_payload["title"],
        kind=asset_payload["kind"],
        source=asset_payload["source"],
        file_path=asset_payload.get("file_path"),
        duration_seconds=asset_payload.get("duration_seconds"),
        sample_rate=asset_payload.get("sample_rate"),
        channels=asset_payload.get("channels"),
        review_status=asset_payload["review_status"],
        rights_status=asset_payload["rights_status"],
        generation_id=asset_payload.get("generation_id"),
        version_details=asset_payload.get("version_details") or {},
        created_at=asset_payload["created_at"],
        updated_at=asset_payload["updated_at"],
        category_assignments=asset_payload.get("category_assignments") or [],
        concept_assignments=asset_payload.get("concept_assignments") or [],
        category_assignment_count=asset_payload.get("category_assignment_count", 0),
        primary_role=asset_payload.get("primary_role"),
    )


def _summary(asset_payload: dict) -> MediaDetailResponse:
    payload = dict(asset_payload)
    payload.setdefault("category_assignments", [])
    payload.setdefault("concept_assignments", [])
    payload.setdefault("category_assignment_count", len(payload["category_assignments"]))
    return _detail(payload)


@router.post("/import", response_model=MediaImportResponse)
async def import_media(
    files: List[UploadFile] = File(...),
    media_service: MediaService = Depends(get_media_service),
):
    uploads = [(file.filename or "", file.file) for file in files if file.filename]
    assets = media_service.import_files(uploads)
    return MediaImportResponse(media=[_summary(asset.model_dump(mode="json")) for asset in assets])


@router.get("", response_model=MediaListResponse)
def list_media(
    review_status: ReviewStatus | None = Query(default=None),
    kind: MediaKind | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    media_service: MediaService = Depends(get_media_service),
):
    assets = media_service.list_media_summaries(review_status=review_status, kind=kind, limit=limit)
    return MediaListResponse(media=[_detail(asset) for asset in assets])


@router.get("/{media_id}/audio")
def stream_media_audio(
    media_id: str,
    media_service: MediaService = Depends(get_media_service),
):
    path = media_service.get_audio_path(media_id)
    return FileResponse(path)


@router.get("/{media_id}", response_model=MediaDetailResponse)
def get_media(
    media_id: str,
    media_service: MediaService = Depends(get_media_service),
):
    return _detail(media_service.get_with_assignments(media_id))


@router.put("/{media_id}/assignments", response_model=MediaDetailResponse)
def upsert_media_assignments(
    media_id: str,
    request: MediaAssignmentsRequest,
    media_service: MediaService = Depends(get_media_service),
):
    payload = media_service.upsert_assignments(
        media_id,
        categories=[item.model_dump() for item in request.categories],
        concepts=[item.model_dump() for item in request.concepts],
        mark_reviewed=request.mark_reviewed,
    )
    return _detail(payload)
