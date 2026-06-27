from __future__ import annotations

from datetime import datetime, timezone

from app.core.errors import ValidationAppError
from app.domain.enums import IngestionStatus
from app.domain.models import MediaAsset, RightsStatus
from app.storage.assignment_store import AssignmentStore
from app.storage.local_media_store import LocalMediaStore


class IngestionService:
    def __init__(self, media_store: LocalMediaStore, assignment_store: AssignmentStore) -> None:
        self.media_store = media_store
        self.assignment_store = assignment_store

    def category_count(self, media_id: str) -> int:
        return len(self.assignment_store.list_category_assignments_for_media(media_id))

    def is_eligible(self, asset: MediaAsset) -> bool:
        if not asset.file_path:
            return False
        if asset.rights_status == RightsStatus.DO_NOT_TRAIN:
            return False
        if self.category_count(asset.id) < 1:
            return False
        if asset.ingestion_status == IngestionStatus.INGESTING:
            return False
        if asset.ingestion_status == IngestionStatus.INGESTED:
            return False
        return asset.ingestion_status in {IngestionStatus.PENDING, IngestionStatus.FAILED}

    def _queue_item(self, asset: MediaAsset) -> dict:
        categories = self.assignment_store.list_category_assignments_for_media(asset.id)
        return {
            "id": asset.id,
            "title": asset.title,
            "duration_seconds": asset.duration_seconds,
            "category_count": len(categories),
            "ingestion_status": asset.ingestion_status.value,
            "review_status": asset.review_status.value,
            "rights_status": asset.rights_status.value,
            "last_training_run_id": asset.last_training_run_id,
            "ingested_at": asset.ingested_at.isoformat() if asset.ingested_at else None,
            "updated_at": asset.updated_at.isoformat(),
        }

    def list_queue(self) -> list[dict]:
        items: list[dict] = []
        for asset in self.media_store.list_recent(limit=10_000):
            if self.is_eligible(asset):
                items.append(self._queue_item(asset))
        items.sort(key=lambda item: item["updated_at"], reverse=True)
        return items

    def list_ingested(self) -> list[dict]:
        items: list[dict] = []
        for asset in self.media_store.list_recent(limit=10_000):
            if asset.ingestion_status == IngestionStatus.INGESTED:
                items.append(self._queue_item(asset))
        items.sort(key=lambda item: item.get("ingested_at") or item["updated_at"], reverse=True)
        return items

    def resolve_media_ids(self, media_ids: list[str] | None) -> list[str]:
        if media_ids is not None:
            if not media_ids:
                raise ValidationAppError("At least one media id is required")
            resolved: list[str] = []
            for media_id in media_ids:
                asset = self.media_store.get(media_id)
                if asset is None:
                    raise ValidationAppError(f"Media asset not found: {media_id}")
                if not self.is_eligible(asset):
                    raise ValidationAppError(f"Media is not eligible for ingestion: {media_id}")
                resolved.append(media_id)
            return list(dict.fromkeys(resolved))

        queued = [item["id"] for item in self.list_queue()]
        if not queued:
            raise ValidationAppError("No eligible media in the ingestion queue")
        return queued

    def mark_ingesting(self, media_ids: list[str], run_id: str) -> None:
        now = datetime.now(timezone.utc)
        for media_id in media_ids:
            asset = self.media_store.get(media_id)
            if asset is None:
                continue
            self.media_store.save(
                asset.model_copy(
                    update={
                        "ingestion_status": IngestionStatus.INGESTING,
                        "last_training_run_id": run_id,
                        "updated_at": now,
                    }
                )
            )

    def finalize_success(self, media_ids: list[str], run_id: str) -> None:
        now = datetime.now(timezone.utc)
        for media_id in media_ids:
            asset = self.media_store.get(media_id)
            if asset is None:
                continue
            self.media_store.save(
                asset.model_copy(
                    update={
                        "ingestion_status": IngestionStatus.INGESTED,
                        "last_training_run_id": run_id,
                        "ingested_at": now,
                        "updated_at": now,
                    }
                )
            )

    def finalize_failure(self, media_ids: list[str], run_id: str) -> None:
        now = datetime.now(timezone.utc)
        for media_id in media_ids:
            asset = self.media_store.get(media_id)
            if asset is None:
                continue
            self.media_store.save(
                asset.model_copy(
                    update={
                        "ingestion_status": IngestionStatus.FAILED,
                        "last_training_run_id": run_id,
                        "updated_at": now,
                    }
                )
            )

    def revert_ingesting(self, media_ids: list[str]) -> None:
        now = datetime.now(timezone.utc)
        for media_id in media_ids:
            asset = self.media_store.get(media_id)
            if asset is None or asset.ingestion_status != IngestionStatus.INGESTING:
                continue
            self.media_store.save(
                asset.model_copy(
                    update={
                        "ingestion_status": IngestionStatus.PENDING,
                        "updated_at": now,
                    }
                )
            )
