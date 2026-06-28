from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

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

    def create_from_run(
        self,
        run: TrainingRun,
        slice_name: str,
        *,
        status: StyleVersionStatus = StyleVersionStatus.ACTIVE,
    ) -> StyleVersion:
        if not run.artifact_path:
            raise ValidationAppError("Training run has no artifact to promote")
        now = datetime.now(timezone.utc)
        record = StyleVersion(
            name=f"{slice_name} style",
            training_run_id=run.id,
            dataset_slice_id=run.dataset_slice_id,
            artifact_path=run.artifact_path,
            backend=run.backend,
            base_model_id=run.base_model_id,
            base_model_name=run.base_model_name,
            training_mode=run.training_mode,
            artifact_type=run.artifact_type,
            status=status,
            created_at=now,
            updated_at=now,
        )
        self.store.save(record)
        return record

    def update_status(self, version_id: str, new_status: StyleVersionStatus) -> StyleVersion:
        record = self.get_required(version_id)
        allowed: dict[StyleVersionStatus, set[StyleVersionStatus]] = {
            StyleVersionStatus.CANDIDATE: {StyleVersionStatus.ACTIVE, StyleVersionStatus.ARCHIVED},
            StyleVersionStatus.ACTIVE: {StyleVersionStatus.ARCHIVED},
            StyleVersionStatus.ARCHIVED: set(),
        }
        if new_status not in allowed.get(record.status, set()):
            raise ValidationAppError(
                f"Cannot transition style version from {record.status} to {new_status}"
            )
        updated = record.model_copy(update={"status": new_status, "updated_at": datetime.now(timezone.utc)})
        self.store.save(updated)
        return updated

    def resolve_load_path(self, version_id: str, data_dir: Path) -> str:
        record = self.get_required(version_id)
        run_id = record.training_run_id
        manifest_path = data_dir / "training_runs" / run_id / "artifacts" / "artifact_manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            load_path = manifest.get("load_path")
            if isinstance(load_path, str) and load_path.strip():
                return load_path.strip()

        artifact = Path(record.artifact_path)
        if artifact.is_absolute():
            return str(artifact)
        return str((data_dir / artifact).resolve())
