from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import AssignmentRole, DatasetSliceStatus
from app.domain.models import ReviewStatus, RightsStatus


class DatasetSliceFilter(BaseModel):
    concept_id: Optional[str] = None
    category_ids: list[str] = Field(default_factory=list)
    roles: list[AssignmentRole] = Field(default_factory=list)
    min_quality: Optional[int] = Field(default=None, ge=1, le=5)
    min_fit: Optional[int] = Field(default=None, ge=1, le=5)
    review_status: Optional[ReviewStatus] = None
    rights_status: Optional[RightsStatus] = None


class DatasetSlice(BaseModel):
    id: str = Field(default_factory=lambda: f"slice_{uuid4().hex}")
    name: str
    slug: str
    description: Optional[str] = None
    filter: DatasetSliceFilter = Field(default_factory=DatasetSliceFilter)
    media_ids: list[str] = Field(default_factory=list)
    frozen_media_ids: list[str] = Field(default_factory=list)
    status: DatasetSliceStatus = DatasetSliceStatus.DRAFT
    version: int = 1
    asset_count: int = 0
    is_auto_generated: bool = False
    lineage_parent_id: Optional[str] = None
    frozen_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("name", "slug")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be empty")
        return value
