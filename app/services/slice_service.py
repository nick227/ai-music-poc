from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from app.core.errors import NotFoundError, ValidationAppError
from app.domain.enums import ConfidenceTier, DatasetSliceStatus
from app.domain.slices import DatasetSlice, DatasetSliceFilter
from app.domain.text_utils import slugify
from app.services.category_service import CategoryService
from app.services.concept_service import ConceptService
from app.services.slice_filter import matches_slice_filter
from app.services.slice_package_service import SlicePackageService
from app.storage.assignment_store import AssignmentStore
from app.storage.local_media_store import LocalMediaStore
from app.storage.slice_store import SliceStore


class SliceService:
    def __init__(
        self,
        slice_store: SliceStore,
        media_store: LocalMediaStore,
        assignment_store: AssignmentStore,
        category_service: CategoryService,
        concept_service: ConceptService,
        package_service: SlicePackageService,
    ) -> None:
        self.slice_store = slice_store
        self.media_store = media_store
        self.assignment_store = assignment_store
        self.category_service = category_service
        self.concept_service = concept_service
        self.package_service = package_service

    def list_slices(self) -> list[DatasetSlice]:
        return self.slice_store.list_all()

    def get_required(self, slice_id: str) -> DatasetSlice:
        record = self.slice_store.get(slice_id)
        if record is None:
            raise NotFoundError(f"Dataset slice not found: {slice_id}")
        return record

    def preview(self, filter: DatasetSliceFilter, limit: int = 200) -> list[dict]:
        self._validate_filter_refs(filter)
        matches: list[dict] = []
        for asset in self.media_store.list_recent(limit=10_000):
            categories = self.assignment_store.list_category_assignments_for_media(asset.id)
            concepts = self.assignment_store.list_concept_assignments_for_media(asset.id)
            if matches_slice_filter(asset, categories, concepts, filter):
                matches.append(self._media_preview(asset.id, asset, categories, concepts))
            if len(matches) >= limit:
                break
        return matches

    def create(
        self,
        name: str,
        filter: DatasetSliceFilter,
        description: str | None = None,
        slug: str | None = None,
        media_ids: list[str] | None = None,
    ) -> DatasetSlice:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationAppError("Slice name is required")
        self._validate_filter_refs(filter)

        resolved_ids = self._resolve_media_ids(filter, media_ids)
        now = datetime.now(timezone.utc)
        record = DatasetSlice(
            name=clean_name,
            slug=slugify(slug or clean_name, fallback="slice"),
            description=description.strip() if description else None,
            filter=filter,
            media_ids=resolved_ids,
            asset_count=len(resolved_ids),
            created_at=now,
            updated_at=now,
        )
        self.slice_store.save(record)
        return record

    def update(
        self,
        slice_id: str,
        name: str | None = None,
        description: str | None = None,
        filter: DatasetSliceFilter | None = None,
        media_ids: list[str] | None = None,
        confidence_tier: ConfidenceTier | None = None,
    ) -> DatasetSlice:
        record = self.get_required(slice_id)
        if record.status == DatasetSliceStatus.ARCHIVED:
            raise ValidationAppError("Archived slices cannot be updated")
        if record.status == DatasetSliceStatus.READY:
            raise ValidationAppError("Ready slices cannot be updated; create a new draft slice instead")

        updates: dict = {"updated_at": datetime.now(timezone.utc)}
        next_filter = filter if filter is not None else record.filter
        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise ValidationAppError("Slice name is required")
            updates["name"] = clean_name
        if description is not None:
            updates["description"] = description.strip() or None

        if filter is not None:
            self._validate_filter_refs(next_filter)
            updates["filter"] = next_filter

        if media_ids is not None:
            resolved_ids = self._resolve_media_ids(next_filter, media_ids)
            updates["media_ids"] = resolved_ids
            updates["asset_count"] = len(resolved_ids)
        elif filter is not None:
            resolved_ids = self._resolve_media_ids(next_filter, None)
            updates["media_ids"] = resolved_ids
            updates["asset_count"] = len(resolved_ids)

        if confidence_tier is not None:
            updates["confidence_tier"] = confidence_tier

        updated = record.model_copy(update=updates)
        self.slice_store.save(updated)
        return updated

    def freeze(self, slice_id: str) -> DatasetSlice:
        record = self.get_required(slice_id)
        if record.status == DatasetSliceStatus.ARCHIVED:
            raise ValidationAppError("Archived slices cannot be frozen")
        if record.status == DatasetSliceStatus.READY and record.frozen_media_ids:
            return record

        if not record.media_ids:
            raise ValidationAppError("Slice has no media to freeze")

        for media_id in record.media_ids:
            asset = self.media_store.get(media_id)
            if asset is None or not asset.file_path:
                raise ValidationAppError(f"Media asset is missing audio: {media_id}")

        frozen_ids = list(record.media_ids)
        self.package_service.copy_audio_for_freeze(record.id, frozen_ids)
        now = datetime.now(timezone.utc)
        tracks = [self._frozen_track_manifest(media_id) for media_id in frozen_ids]
        manifest = {
            "format_version": 1,
            "slice_id": record.id,
            "name": record.name,
            "version": record.version,
            "concept_id": record.filter.concept_id,
            "track_count": len(frozen_ids),
            "total_duration_seconds": round(sum(item.get("duration_seconds") or 0 for item in tracks), 3),
            "filters": record.filter.model_dump(mode="json"),
            "media_ids": frozen_ids,
            "tracks": tracks,
            "frozen_at": now.isoformat(),
        }
        manifest["manifest_hash"] = self._manifest_hash(manifest)
        self.slice_store.write_manifest(record.id, manifest)

        updated = record.model_copy(
            update={
                "frozen_media_ids": frozen_ids,
                "status": DatasetSliceStatus.READY,
                "asset_count": len(frozen_ids),
                "frozen_at": now,
                "updated_at": now,
            }
        )
        self.slice_store.save(updated)
        return updated

    def create_and_freeze(self, name: str, media_ids: list[str]) -> DatasetSlice:
        if not media_ids:
            raise ValidationAppError("At least one media id is required")
        record = self.create(name, DatasetSliceFilter(), media_ids=media_ids)
        return self.freeze(record.id)

    def build_package_path(self, slice_id: str):
        record = self.get_required(slice_id)
        if record.status != DatasetSliceStatus.READY:
            raise ValidationAppError("Slice must be frozen before downloading a package")
        if not record.frozen_media_ids:
            raise ValidationAppError("Slice has no frozen media")
        return self.package_service.create_package(record)

    def _resolve_media_ids(self, filter: DatasetSliceFilter, media_ids: list[str] | None) -> list[str]:
        if media_ids is not None:
            if not media_ids:
                return []
            for media_id in media_ids:
                asset = self.media_store.get(media_id)
                if asset is None:
                    raise ValidationAppError(f"Media asset not found: {media_id}")
            return list(dict.fromkeys(media_ids))

        preview = self.preview(filter)
        return [item["id"] for item in preview]

    def _validate_filter_refs(self, filter: DatasetSliceFilter) -> None:
        if filter.concept_id is not None:
            self.concept_service.get_required(filter.concept_id)
        for category_id in filter.category_ids:
            self.category_service.get_required(category_id)

    def _media_preview(self, media_id, asset, categories, concepts) -> dict:
        return {
            "id": media_id,
            "title": asset.title,
            "kind": asset.kind.value,
            "review_status": asset.review_status.value,
            "rights_status": asset.rights_status.value,
            "duration_seconds": asset.duration_seconds,
            "category_assignment_count": len(categories),
            "concept_assignment_count": len(concepts),
            "category_ids": [item.category_id for item in categories],
            "concept_ids": [item.concept_id for item in concepts],
            "primary_role": categories[0].role.value if categories else (concepts[0].role.value if concepts else None),
        }

    def _frozen_track_manifest(self, media_id: str) -> dict:
        asset = self.media_store.get(media_id)
        categories = self.assignment_store.list_category_assignments_for_media(media_id)
        category_rows = []
        for assignment in categories:
            category = self.category_service.get_required(assignment.category_id)
            category_rows.append(
                {
                    "category_id": category.id,
                    "name": category.name,
                    "slug": category.slug,
                    "dimension": category.dimension.value,
                    "role": assignment.role.value,
                    "quality_score": assignment.quality_score,
                    "fit_score": assignment.fit_score,
                }
            )
        return {
            "media_id": media_id,
            "title": asset.title if asset else "",
            "file_path": asset.file_path if asset else None,
            "duration_seconds": asset.duration_seconds if asset else None,
            "sample_rate": asset.sample_rate if asset else None,
            "channels": asset.channels if asset else None,
            "categories": category_rows,
        }

    @staticmethod
    def _manifest_hash(manifest: dict) -> str:
        payload = {key: value for key, value in manifest.items() if key != "manifest_hash"}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
