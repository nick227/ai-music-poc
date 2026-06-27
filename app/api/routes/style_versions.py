from fastapi import APIRouter, Depends

from app.api.dependencies import get_style_version_service
from app.api.schemas.style_versions_api import StyleVersionListResponse, StyleVersionResponse, style_version_to_response
from app.services.style_version_service import StyleVersionService

router = APIRouter(prefix="/api/style-versions", tags=["style-versions"])


@router.get("", response_model=StyleVersionListResponse)
def list_style_versions(style_service: StyleVersionService = Depends(get_style_version_service)):
    versions = [style_version_to_response(item) for item in style_service.list_versions()]
    return StyleVersionListResponse(style_versions=versions)


@router.get("/{version_id}", response_model=StyleVersionResponse)
def get_style_version(
    version_id: str,
    style_service: StyleVersionService = Depends(get_style_version_service),
):
    return style_version_to_response(style_service.get_required(version_id))
