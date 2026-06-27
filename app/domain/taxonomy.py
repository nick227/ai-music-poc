from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import (
    AssignmentRole,
    CategoryDimension,
    CategoryStatus,
    ConceptStatus,
    CoverageState,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Category(BaseModel):
    id: str
    dimension: CategoryDimension
    name: str
    slug: str
    description: Optional[str] = None
    status: CategoryStatus = CategoryStatus.ACTIVE
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class Concept(BaseModel):
    id: str = Field(default_factory=lambda: f"concept_{uuid4().hex}")
    name: str
    slug: str
    description: Optional[str] = None
    category_ids: list[str] = Field(default_factory=list)
    status: ConceptStatus = ConceptStatus.ACTIVE
    coverage_state: CoverageState = CoverageState.EMPTY
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    @field_validator("name", "slug")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be empty")
        return value


class MediaCategoryAssignment(BaseModel):
    id: str = Field(default_factory=lambda: f"mca_{uuid4().hex}")
    media_asset_id: str
    category_id: str
    quality_score: Optional[int] = Field(default=None, ge=1, le=5)
    fit_score: Optional[int] = Field(default=None, ge=1, le=5)
    role: AssignmentRole = AssignmentRole.REFERENCE
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notes: Optional[str] = None
    reviewed: bool = False
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class MediaConceptAssignment(BaseModel):
    id: str = Field(default_factory=lambda: f"mco_{uuid4().hex}")
    media_asset_id: str
    concept_id: str
    quality_score: Optional[int] = Field(default=None, ge=1, le=5)
    fit_score: Optional[int] = Field(default=None, ge=1, le=5)
    role: AssignmentRole = AssignmentRole.REFERENCE
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notes: Optional[str] = None
    reviewed: bool = False
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
