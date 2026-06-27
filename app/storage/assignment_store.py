from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.domain.taxonomy import MediaCategoryAssignment, MediaConceptAssignment
from app.storage.json_entity_store import JsonEntityStore


class AssignmentStore:
    def __init__(self, directory: Path) -> None:
        self.category_store = JsonEntityStore[MediaCategoryAssignment](directory / "categories", MediaCategoryAssignment)
        self.concept_store = JsonEntityStore[MediaConceptAssignment](directory / "concepts", MediaConceptAssignment)
        self.category_store.directory.mkdir(parents=True, exist_ok=True)
        self.concept_store.directory.mkdir(parents=True, exist_ok=True)

    def find_category_assignment(self, media_asset_id: str, category_id: str) -> MediaCategoryAssignment | None:
        for item in self.category_store.list_all():
            if item.media_asset_id == media_asset_id and item.category_id == category_id:
                return item
        return None

    def find_concept_assignment(self, media_asset_id: str, concept_id: str) -> MediaConceptAssignment | None:
        for item in self.concept_store.list_all():
            if item.media_asset_id == media_asset_id and item.concept_id == concept_id:
                return item
        return None

    def upsert_category_assignment(self, assignment: MediaCategoryAssignment) -> MediaCategoryAssignment:
        existing = self.find_category_assignment(assignment.media_asset_id, assignment.category_id)
        now = datetime.now(timezone.utc)
        if existing is not None:
            updated = existing.model_copy(
                update={
                    "quality_score": assignment.quality_score,
                    "fit_score": assignment.fit_score,
                    "role": assignment.role,
                    "confidence": assignment.confidence,
                    "notes": assignment.notes,
                    "reviewed": assignment.reviewed,
                    "updated_at": now,
                }
            )
            self.category_store.save(updated)
            return updated
        self.category_store.save(assignment)
        return assignment

    def upsert_concept_assignment(self, assignment: MediaConceptAssignment) -> MediaConceptAssignment:
        existing = self.find_concept_assignment(assignment.media_asset_id, assignment.concept_id)
        now = datetime.now(timezone.utc)
        if existing is not None:
            updated = existing.model_copy(
                update={
                    "quality_score": assignment.quality_score,
                    "fit_score": assignment.fit_score,
                    "role": assignment.role,
                    "confidence": assignment.confidence,
                    "notes": assignment.notes,
                    "reviewed": assignment.reviewed,
                    "updated_at": now,
                }
            )
            self.concept_store.save(updated)
            return updated
        self.concept_store.save(assignment)
        return assignment

    def list_category_assignments_for_media(self, media_asset_id: str) -> list[MediaCategoryAssignment]:
        items = [item for item in self.category_store.list_all() if item.media_asset_id == media_asset_id]
        items.sort(key=lambda item: item.created_at)
        return items

    def list_concept_assignments_for_media(self, media_asset_id: str) -> list[MediaConceptAssignment]:
        items = [item for item in self.concept_store.list_all() if item.media_asset_id == media_asset_id]
        items.sort(key=lambda item: item.created_at)
        return items
