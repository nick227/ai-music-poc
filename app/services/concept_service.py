from __future__ import annotations

from datetime import datetime, timezone

from app.core.errors import NotFoundError, ValidationAppError
from app.domain.enums import ConceptStatus, CoverageState
from app.domain.taxonomy import Concept
from app.domain.text_utils import slugify
from app.services.category_service import CategoryService
from app.storage.concept_store import ConceptStore


class ConceptService:
    def __init__(self, store: ConceptStore, category_service: CategoryService) -> None:
        self.store = store
        self.category_service = category_service

    def create(self, name: str, category_ids: list[str], slug: str | None = None, description: str | None = None) -> Concept:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationAppError("Concept name is required")
        if not category_ids:
            raise ValidationAppError("At least one category_id is required")

        unique_category_ids: list[str] = []
        for category_id in category_ids:
            if category_id not in unique_category_ids:
                self.category_service.get_required(category_id)
                unique_category_ids.append(category_id)

        clean_slug = slugify(slug or clean_name, fallback="concept")
        concept = Concept(
            name=clean_name,
            slug=clean_slug,
            description=description.strip() if description else None,
            category_ids=unique_category_ids,
            status=ConceptStatus.ACTIVE,
            coverage_state=CoverageState.EMPTY,
        )
        self.store.save(concept)
        return concept

    def list(self) -> list[Concept]:
        return self.store.list_sorted()

    def get_required(self, concept_id: str) -> Concept:
        concept = self.store.get(concept_id)
        if concept is None:
            raise NotFoundError(f"Concept not found: {concept_id}")
        return concept

    def touch_updated(self, concept: Concept) -> Concept:
        updated = concept.model_copy(update={"updated_at": datetime.now(timezone.utc)})
        self.store.save(updated)
        return updated
