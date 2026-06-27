from __future__ import annotations

import shutil
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Optional

from app.core.config import Settings
from app.core.errors import NotFoundError, ValidationAppError
from app.core.paths import safe_child_path
from app.domain.enums import AssignmentRole
from app.domain.models import MediaAsset, MediaKind, MediaSource, ReviewStatus
from app.domain.taxonomy import MediaCategoryAssignment, MediaConceptAssignment
from app.services.category_service import CategoryService
from app.services.concept_service import ConceptService
from app.storage.assignment_store import AssignmentStore
from app.storage.local_media_store import LocalMediaStore

ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


class MediaService:
    def __init__(
        self,
        media_store: LocalMediaStore,
        assignment_store: AssignmentStore,
        category_service: CategoryService,
        concept_service: ConceptService,
        settings: Settings,
    ) -> None:
        self.media_store = media_store
        self.assignment_store = assignment_store
        self.category_service = category_service
        self.concept_service = concept_service
        self.settings = settings

    def import_files(self, uploads: list[tuple[str, BinaryIO]]) -> list[MediaAsset]:
        if not uploads:
            raise ValidationAppError("At least one audio file is required")

        created: list[MediaAsset] = []
        for original_name, stream in uploads:
            created.append(self._import_one(original_name, stream))
        return created

    def list_media(
        self,
        review_status: Optional[ReviewStatus] = None,
        kind: Optional[MediaKind] = None,
        limit: int = 50,
    ) -> list[MediaAsset]:
        return self.media_store.list_filtered(review_status=review_status, kind=kind, limit=limit)

    def list_media_summaries(
        self,
        review_status: Optional[ReviewStatus] = None,
        kind: Optional[MediaKind] = None,
        limit: int = 50,
    ) -> list[dict]:
        return [self._list_summary(asset) for asset in self.list_media(review_status=review_status, kind=kind, limit=limit)]

    def _list_summary(self, asset: MediaAsset) -> dict:
        category_assignments = self.assignment_store.list_category_assignments_for_media(asset.id)
        primary = category_assignments[0] if category_assignments else None
        return {
            **asset.model_dump(mode="json"),
            "category_assignments": [],
            "concept_assignments": [],
            "category_assignment_count": len(category_assignments),
            "primary_role": primary.role.value if primary else None,
        }

    def get_with_assignments(self, media_id: str) -> dict:
        asset = self.media_store.get(media_id)
        if asset is None:
            raise NotFoundError(f"Media asset not found: {media_id}")
        return self._with_assignments(asset)

    def upsert_assignments(
        self,
        media_id: str,
        categories: list[dict],
        concepts: list[dict],
        mark_reviewed: bool = False,
    ) -> dict:
        asset = self.media_store.get(media_id)
        if asset is None:
            raise NotFoundError(f"Media asset not found: {media_id}")

        category_assignments: list[MediaCategoryAssignment] = []
        for item in categories:
            category_id = item["category_id"]
            self.category_service.get_required(category_id)
            assignment = MediaCategoryAssignment(
                media_asset_id=media_id,
                category_id=category_id,
                quality_score=item.get("quality_score"),
                fit_score=item.get("fit_score"),
                role=item.get("role", AssignmentRole.REFERENCE),
                confidence=item.get("confidence"),
                notes=item.get("notes"),
                reviewed=item.get("reviewed", False),
            )
            category_assignments.append(self.assignment_store.upsert_category_assignment(assignment))

        concept_assignments: list[MediaConceptAssignment] = []
        for item in concepts:
            concept_id = item["concept_id"]
            self.concept_service.get_required(concept_id)
            assignment = MediaConceptAssignment(
                media_asset_id=media_id,
                concept_id=concept_id,
                quality_score=item.get("quality_score"),
                fit_score=item.get("fit_score"),
                role=item.get("role", AssignmentRole.REFERENCE),
                confidence=item.get("confidence"),
                notes=item.get("notes"),
                reviewed=item.get("reviewed", False),
            )
            concept_assignments.append(self.assignment_store.upsert_concept_assignment(assignment))

        update_fields: dict = {"updated_at": datetime.now(timezone.utc)}
        if mark_reviewed:
            update_fields["review_status"] = ReviewStatus.REVIEWED
        updated_asset = asset.model_copy(update=update_fields)
        self.media_store.save(updated_asset)

        return {
            **updated_asset.model_dump(mode="json"),
            "category_assignments": [item.model_dump(mode="json") for item in category_assignments],
            "concept_assignments": [item.model_dump(mode="json") for item in concept_assignments],
        }

    def get_audio_path(self, media_id: str) -> Path:
        asset = self.media_store.get(media_id)
        if asset is None:
            raise NotFoundError(f"Media asset not found: {media_id}")
        if not asset.file_path:
            raise NotFoundError(f"Media asset has no audio file: {media_id}")
        return safe_child_path(self.settings.data_dir, asset.file_path)

    def _import_one(self, original_name: str, stream: BinaryIO) -> MediaAsset:
        filename = Path(original_name).name
        if not filename:
            raise ValidationAppError("Uploaded file must have a filename")

        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_AUDIO_EXTENSIONS:
            raise ValidationAppError(f"Unsupported audio extension: {extension or '(none)'}")

        asset = MediaAsset(
            title=Path(filename).stem,
            kind=MediaKind.UPLOAD,
            source=MediaSource.USER_IMPORT,
            review_status=ReviewStatus.NEEDS_REVIEW,
        )
        dest_name = f"{asset.id}{extension}"
        dest_path = safe_child_path(self.settings.uploads_dir, dest_name)

        with dest_path.open("wb") as handle:
            shutil.copyfileobj(stream, handle)

        duration_seconds, sample_rate, channels = _probe_audio(dest_path, extension)
        asset = asset.model_copy(
            update={
                "file_path": f"uploads/{dest_name}",
                "duration_seconds": duration_seconds,
                "sample_rate": sample_rate,
                "channels": channels,
            }
        )
        self.media_store.save(asset)
        return asset

    def _with_assignments(self, asset: MediaAsset) -> dict:
        category_assignments = self.assignment_store.list_category_assignments_for_media(asset.id)
        concept_assignments = self.assignment_store.list_concept_assignments_for_media(asset.id)
        primary = category_assignments[0] if category_assignments else None
        return {
            **asset.model_dump(mode="json"),
            "category_assignments": [item.model_dump(mode="json") for item in category_assignments],
            "concept_assignments": [item.model_dump(mode="json") for item in concept_assignments],
            "category_assignment_count": len(category_assignments),
            "primary_role": primary.role.value if primary else None,
        }


def _probe_audio(path: Path, extension: str) -> tuple[Optional[float], Optional[int], Optional[int]]:
    if extension != ".wav":
        return None, None, None
    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_rate = handle.getframerate()
            frame_count = handle.getnframes()
            duration = frame_count / float(sample_rate or 1)
            return round(duration, 3), sample_rate, channels
    except wave.Error:
        return None, None, None
