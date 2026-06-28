from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.domain.enums import AssignmentRole, ConfidenceTier, DatasetSliceStatus
from app.domain.models import ReviewStatus, RightsStatus
from app.domain.slices import DatasetSlice, DatasetSliceFilter


class SliceFilterInput(BaseModel):
    concept_id: Optional[str] = None
    category_ids: list[str] = Field(default_factory=list)
    roles: list[AssignmentRole] = Field(default_factory=list)
    min_quality: Optional[int] = Field(default=None, ge=1, le=5)
    min_fit: Optional[int] = Field(default=None, ge=1, le=5)
    review_status: Optional[ReviewStatus] = None
    rights_status: Optional[RightsStatus] = None

    def to_filter(self) -> DatasetSliceFilter:
        return DatasetSliceFilter.model_validate(self.model_dump())


class SliceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    slug: Optional[str] = Field(default=None, max_length=160)
    filter: SliceFilterInput = Field(default_factory=SliceFilterInput)
    media_ids: Optional[list[str]] = None


class SliceUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    filter: Optional[SliceFilterInput] = None
    media_ids: Optional[list[str]] = None


class SliceResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    filter: DatasetSliceFilter
    media_ids: list[str]
    frozen_media_ids: list[str]
    status: DatasetSliceStatus
    version: int
    asset_count: int
    is_auto_generated: bool = False
    confidence_tier: ConfidenceTier = ConfidenceTier.CANDIDATE
    lineage_parent_id: Optional[str] = None
    frozen_at: Optional[str] = None
    created_at: str
    updated_at: str


class SliceListResponse(BaseModel):
    slices: list[SliceResponse]


class SlicePreviewItem(BaseModel):
    id: str
    title: str
    kind: str
    review_status: str
    rights_status: str
    duration_seconds: Optional[float] = None
    category_assignment_count: int = 0
    concept_assignment_count: int = 0
    category_ids: list[str] = Field(default_factory=list)
    concept_ids: list[str] = Field(default_factory=list)
    primary_role: Optional[str] = None


class SlicePreviewResponse(BaseModel):
    media: list[SlicePreviewItem]
    count: int


def slice_to_response(record: DatasetSlice) -> SliceResponse:
    return SliceResponse(
        id=record.id,
        name=record.name,
        slug=record.slug,
        description=record.description,
        filter=record.filter,
        media_ids=record.media_ids,
        frozen_media_ids=record.frozen_media_ids,
        status=record.status,
        version=record.version,
        asset_count=record.asset_count,
        is_auto_generated=record.is_auto_generated,
        confidence_tier=record.confidence_tier,
        lineage_parent_id=record.lineage_parent_id,
        frozen_at=record.frozen_at.isoformat() if record.frozen_at else None,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )
