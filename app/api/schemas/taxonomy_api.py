from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.domain.enums import AssignmentRole
from app.domain.taxonomy import Category, Concept, MediaCategoryAssignment, MediaConceptAssignment


class CategoryListResponse(BaseModel):
    categories: list[Category]


class ConceptCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: Optional[str] = Field(default=None, max_length=160)
    description: Optional[str] = Field(default=None, max_length=2000)
    category_ids: list[str] = Field(min_length=1)


class ConceptListResponse(BaseModel):
    concepts: list[Concept]


class CategoryAssignmentInput(BaseModel):
    category_id: str
    quality_score: Optional[int] = Field(default=None, ge=1, le=5)
    fit_score: Optional[int] = Field(default=None, ge=1, le=5)
    role: AssignmentRole = AssignmentRole.REFERENCE
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notes: Optional[str] = Field(default=None, max_length=4000)
    reviewed: bool = False


class ConceptAssignmentInput(BaseModel):
    concept_id: str
    quality_score: Optional[int] = Field(default=None, ge=1, le=5)
    fit_score: Optional[int] = Field(default=None, ge=1, le=5)
    role: AssignmentRole = AssignmentRole.REFERENCE
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notes: Optional[str] = Field(default=None, max_length=4000)
    reviewed: bool = False


class MediaAssignmentsRequest(BaseModel):
    categories: list[CategoryAssignmentInput] = Field(default_factory=list)
    concepts: list[ConceptAssignmentInput] = Field(default_factory=list)
    mark_reviewed: bool = False


class MediaDetailResponse(BaseModel):
    id: str
    title: str
    kind: str
    source: str
    file_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    review_status: str
    rights_status: str
    generation_id: Optional[str] = None
    version_details: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str
    category_assignments: list[MediaCategoryAssignment]
    concept_assignments: list[MediaConceptAssignment]


class MediaImportResponse(BaseModel):
    media: list[MediaDetailResponse]


class MediaListResponse(BaseModel):
    media: list[MediaDetailResponse]
