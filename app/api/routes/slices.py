from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from app.api.dependencies import get_slice_service
from app.api.schemas.slices_api import (
    SliceCreateRequest,
    SliceFilterInput,
    SliceListResponse,
    SlicePreviewResponse,
    SliceResponse,
    SliceUpdateRequest,
    slice_to_response,
)
from app.domain.enums import AssignmentRole
from app.domain.models import ReviewStatus, RightsStatus
from app.services.slice_service import SliceService

router = APIRouter(prefix="/api/slices", tags=["slices"])


def _preview_filter(
    concept_id: str | None = Query(default=None),
    category_ids: list[str] = Query(default=[]),
    roles: list[AssignmentRole] = Query(default=[]),
    min_quality: int | None = Query(default=None, ge=1, le=5),
    min_fit: int | None = Query(default=None, ge=1, le=5),
    review_status: ReviewStatus | None = Query(default=None),
    rights_status: RightsStatus | None = Query(default=None),
) -> SliceFilterInput:
    return SliceFilterInput(
        concept_id=concept_id,
        category_ids=category_ids,
        roles=roles,
        min_quality=min_quality,
        min_fit=min_fit,
        review_status=review_status,
        rights_status=rights_status,
    )


@router.get("/preview", response_model=SlicePreviewResponse)
def preview_slices(
    filter: SliceFilterInput = Depends(_preview_filter),
    limit: int = Query(default=200, ge=1, le=500),
    slice_service: SliceService = Depends(get_slice_service),
):
    media = slice_service.preview(filter.to_filter(), limit=limit)
    return SlicePreviewResponse(media=media, count=len(media))


@router.get("", response_model=SliceListResponse)
def list_slices(slice_service: SliceService = Depends(get_slice_service)):
    slices = [slice_to_response(item) for item in slice_service.list_slices()]
    return SliceListResponse(slices=slices)


@router.post("", response_model=SliceResponse)
def create_slice(
    request: SliceCreateRequest,
    slice_service: SliceService = Depends(get_slice_service),
):
    record = slice_service.create(
        name=request.name,
        description=request.description,
        slug=request.slug,
        filter=request.filter.to_filter(),
        media_ids=request.media_ids,
    )
    return slice_to_response(record)


@router.get("/{slice_id}", response_model=SliceResponse)
def get_slice(
    slice_id: str,
    slice_service: SliceService = Depends(get_slice_service),
):
    return slice_to_response(slice_service.get_required(slice_id))


@router.put("/{slice_id}", response_model=SliceResponse)
def update_slice(
    slice_id: str,
    request: SliceUpdateRequest,
    slice_service: SliceService = Depends(get_slice_service),
):
    record = slice_service.update(
        slice_id,
        name=request.name,
        description=request.description,
        filter=request.filter.to_filter() if request.filter is not None else None,
        media_ids=request.media_ids,
    )
    return slice_to_response(record)


@router.post("/{slice_id}/freeze", response_model=SliceResponse)
def freeze_slice(
    slice_id: str,
    slice_service: SliceService = Depends(get_slice_service),
):
    return slice_to_response(slice_service.freeze(slice_id))


@router.get("/{slice_id}/package")
def download_slice_package(
    slice_id: str,
    slice_service: SliceService = Depends(get_slice_service),
):
    record = slice_service.get_required(slice_id)
    path = slice_service.build_package_path(slice_id)
    filename = f"{record.slug}-v{record.version}-package.zip"
    return FileResponse(path, media_type="application/zip", filename=filename)
