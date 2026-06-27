from __future__ import annotations

from datetime import datetime, timezone

from app.core.errors import NotFoundError, ValidationAppError
from app.domain.enums import IngestionStatus, StyleVersionStatus
from app.domain.models import RightsStatus
from app.domain.style_versions import StyleVersion
from app.domain.training import TrainingRun
from app.storage.style_version_store import StyleVersionStore


class StyleVersionService:
    def __init__(self, store: StyleVersionStore) -> None:
        self.store = store

    def list_versions(self) -> list[StyleVersion]:
        return self.store.list_all()

    def list_active(self) -> list[StyleVersion]:
        return [item for item in self.list_versions() if item.status == StyleVersionStatus.ACTIVE]

    def get_required(self, version_id: str) -> StyleVersion:
        record = self.store.get(version_id)
        if record is None:
            raise NotFoundError(f"Style version not found: {version_id}")
        return record

    def create_from_run(self, run: TrainingRun, slice_name: str) -> StyleVersion:
        if not run.artifact_path:
            raise ValidationAppError("Training run has no artifact to promote")
        now = datetime.now(timezone.utc)
        record = StyleVersion(
            name=f"{slice_name} style",
            training_run_id=run.id,
            dataset_slice_id=run.dataset_slice_id,
            artifact_path=run.artifact_path,
            backend=run.backend,
            status=StyleVersionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        self.store.save(record)
        return record
