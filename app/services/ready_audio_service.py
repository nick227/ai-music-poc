from __future__ import annotations

from datetime import datetime

from app.core.errors import ValidationAppError
from app.domain.enums import AssignmentRole, IngestionStatus
from app.domain.models import MediaAsset, ReviewStatus, RightsStatus
from app.domain.tag_fingerprint import already_ingested_with_fingerprint
from app.domain.taxonomy import MediaCategoryAssignment, MediaConceptAssignment
from app.services.category_service import CategoryService
from app.services.concept_service import ConceptService
from app.storage.assignment_store import AssignmentStore
from app.storage.local_media_store import LocalMediaStore

_ROLE_PRIORITY: dict[AssignmentRole, int] = {
    AssignmentRole.GOLD_REFERENCE: 0,
    AssignmentRole.TRAINING_CANDIDATE: 1,
    AssignmentRole.REFERENCE: 2,
}
_DEFAULT_ROLE_PRIORITY = 50


class ReadyAudioService:
    def __init__(
        self,
        media_store: LocalMediaStore,
        assignment_store: AssignmentStore,
        concept_service: ConceptService,
        category_service: CategoryService,
    ) -> None:
        self.media_store = media_store
        self.assignment_store = assignment_store
        self.concept_service = concept_service
        self.category_service = category_service

    def is_ready(
        self,
        asset: MediaAsset,
        categories: list[MediaCategoryAssignment],
        concepts: list[MediaConceptAssignment],
    ) -> bool:
        if not asset.file_path:
            return False
        if asset.rights_status == RightsStatus.DO_NOT_TRAIN:
            return False
        if asset.review_status == ReviewStatus.REJECTED:
            return False
        if not categories and not concepts:
            return False
        if asset.ingestion_status == IngestionStatus.INGESTING:
            return False
        if already_ingested_with_fingerprint(
            asset.ingested_fingerprint,
            asset.ingestion_status,
            categories,
            concepts,
        ):
            return False
        return True

    def list_ready(self, concept_id: str | None = None) -> dict:
        if concept_id is not None:
            self.concept_service.get_required(concept_id)

        entries: list[dict] = []
        for asset in self.media_store.list_recent(limit=10_000):
            categories = self.assignment_store.list_category_assignments_for_media(asset.id)
            concepts = self.assignment_store.list_concept_assignments_for_media(asset.id)
            if not self.is_ready(asset, categories, concepts):
                continue
            entries.append(self._entry(asset, categories, concepts))

        ranked = sorted(
            entries,
            key=lambda item: self._sort_key(item, concept_id),
        )
        return {
            "concept_id": concept_id,
            "total": len(ranked),
            "groups": self._group_entries(ranked, concept_id),
            "items": ranked,
        }

    def resolve_for_package(self, concept_id: str | None, media_ids: list[str] | None) -> list[str]:
        if media_ids:
            resolved: list[str] = []
            for media_id in media_ids:
                asset = self.media_store.get(media_id)
                if asset is None:
                    raise ValidationAppError(f"Media asset not found: {media_id}")
                categories = self.assignment_store.list_category_assignments_for_media(media_id)
                concepts = self.assignment_store.list_concept_assignments_for_media(media_id)
                if not self.is_ready(asset, categories, concepts):
                    raise ValidationAppError(f"Media is not ready audio: {media_id}")
                resolved.append(media_id)
            return list(dict.fromkeys(resolved))

        ready = self.list_ready(concept_id)["items"]
        if not ready:
            raise ValidationAppError("No ready audio available to package")
        return [item["id"] for item in ready]

    def _entry(
        self,
        asset: MediaAsset,
        categories: list[MediaCategoryAssignment],
        concepts: list[MediaConceptAssignment],
    ) -> dict:
        roles = {item.role for item in categories} | {item.role for item in concepts}
        quality = self._best_score([item.quality_score for item in categories + concepts])
        fit = self._best_score([item.fit_score for item in categories + concepts])
        concept_ids = [item.concept_id for item in concepts]
        category_ids = [item.category_id for item in categories]
        primary_role = self._primary_role(roles)
        group_label = self._group_label(concept_ids, category_ids)
        return {
            "id": asset.id,
            "title": asset.title,
            "duration_seconds": asset.duration_seconds,
            "category_count": len(categories),
            "concept_count": len(concepts),
            "concept_ids": concept_ids,
            "category_ids": category_ids,
            "primary_role": primary_role.value if primary_role else None,
            "quality_score": quality,
            "fit_score": fit,
            "ingestion_status": asset.ingestion_status.value,
            "updated_at": asset.updated_at.isoformat(),
            "group_label": group_label,
        }

    def _sort_key(self, item: dict, concept_id: str | None) -> tuple:
        concept_match = 1
        concept_category_overlap = 0
        if concept_id:
            if concept_id in item["concept_ids"]:
                concept_match = 0
            concept = self.concept_service.get_required(concept_id)
            concept_category_overlap = len(set(item["category_ids"]).intersection(set(concept.category_ids)))

        if item["primary_role"] is not None:
            role = _ROLE_PRIORITY.get(AssignmentRole(item["primary_role"]), _DEFAULT_ROLE_PRIORITY)
        else:
            role = _DEFAULT_ROLE_PRIORITY

        quality = item["quality_score"] or 0
        fit = item["fit_score"] or 0
        updated = item["updated_at"].replace("Z", "+00:00")
        recency = -datetime.fromisoformat(updated).timestamp()
        return (concept_match, -concept_category_overlap, role, -quality, -fit, recency)

    def _group_entries(self, items: list[dict], concept_id: str | None) -> list[dict]:
        if concept_id:
            concept = self.concept_service.get_required(concept_id)
            return [{"label": concept.name, "concept_id": concept_id, "items": items}]

        grouped: dict[str, list[dict]] = {}
        for item in items:
            label = item["group_label"]
            grouped.setdefault(label, []).append(item)
        return [
            {"label": label, "concept_id": None, "items": grouped[label]}
            for label in sorted(grouped.keys(), key=str.lower)
        ]

    def _group_label(self, concept_ids: list[str], category_ids: list[str]) -> str:
        if concept_ids:
            concept = self.concept_service.get_required(concept_ids[0])
            return concept.name
        if category_ids:
            category = self.category_service.get_required(category_ids[0])
            return f"{category.dimension.replace('_', ' ').title()}: {category.name}"
        return "Uncategorized"

    @staticmethod
    def _best_score(values: list[int | None]) -> int | None:
        scored = [value for value in values if value is not None]
        return max(scored) if scored else None

    @staticmethod
    def _primary_role(roles: set[AssignmentRole]) -> AssignmentRole | None:
        for role in (AssignmentRole.GOLD_REFERENCE, AssignmentRole.TRAINING_CANDIDATE, AssignmentRole.REFERENCE):
            if role in roles:
                return role
        return next(iter(roles), None)
