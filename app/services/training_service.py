from __future__ import annotations

from datetime import datetime, timezone

from app.core.errors import NotFoundError, ValidationAppError
from app.core.config import Settings
from app.domain.enums import DatasetSliceStatus
from app.domain.models import JobStatus
from app.domain.training import TrainingRun
from app.domain.training_presets import TRAINING_PRESETS, resolve_training_preset
from app.services.ingestion_service import IngestionService
from app.services.slice_service import SliceService
from app.services.style_version_service import StyleVersionService
from app.storage.training_run_store import TrainingRunStore
from app.training.mock_adapter import MockTrainingAdapter


class TrainingService:
    def __init__(
        self,
        store: TrainingRunStore,
        slice_service: SliceService,
        adapter: MockTrainingAdapter,
        ingestion_service: IngestionService,
        style_version_service: StyleVersionService,
        settings: Settings,
    ) -> None:
        self.store = store
        self.slice_service = slice_service
        self.adapter = adapter
        self.ingestion_service = ingestion_service
        self.style_version_service = style_version_service
        self.settings = settings

    def list_runs(self) -> list[TrainingRun]:
        return self.store.list_all()

    def get_required(self, run_id: str) -> TrainingRun:
        run = self.store.get(run_id)
        if run is None:
            raise NotFoundError(f"Training run not found: {run_id}")
        return run

    def list_queue(self) -> list[dict]:
        return self.ingestion_service.list_queue()

    def list_ingested(self) -> list[dict]:
        return self.ingestion_service.list_ingested()

    def ingest(
        self,
        media_ids: list[str] | None = None,
        name: str | None = None,
        config_preset: str = "calibration",
    ) -> TrainingRun:
        if not self.settings.training_enabled:
            raise ValidationAppError("Training is disabled")

        if config_preset not in TRAINING_PRESETS:
            raise ValidationAppError(f"Unknown config preset: {config_preset}")

        if self.store.find_active_run() is not None:
            raise ValidationAppError("Another training run is already active")

        resolved_ids = self.ingestion_service.resolve_media_ids(media_ids)
        run_name = (name or f"Ingest {len(resolved_ids)} track{'s' if len(resolved_ids) != 1 else ''}").strip()
        slice_name = f"{run_name} snapshot"

        frozen_slice = self.slice_service.create_and_freeze(slice_name, resolved_ids)
        run = self._create_run_record(run_name, frozen_slice.id, config_preset)
        self.ingestion_service.mark_ingesting(resolved_ids, run.id)
        return run

    def create_run(self, name: str, dataset_slice_id: str, config_preset: str) -> TrainingRun:
        if not self.settings.training_enabled:
            raise ValidationAppError("Training is disabled")

        clean_name = name.strip()
        if not clean_name:
            raise ValidationAppError("Training run name is required")

        if config_preset not in TRAINING_PRESETS:
            raise ValidationAppError(f"Unknown config preset: {config_preset}")

        slice_record = self.slice_service.get_required(dataset_slice_id)
        if slice_record.status != DatasetSliceStatus.READY:
            raise ValidationAppError("Dataset slice must be READY before starting training")
        if not slice_record.frozen_media_ids:
            raise ValidationAppError("Dataset slice has no frozen media")

        if self.store.find_active_run() is not None:
            raise ValidationAppError("Another training run is already active")

        return self._create_run_record(clean_name, dataset_slice_id, config_preset)

    def _create_run_record(self, name: str, dataset_slice_id: str, config_preset: str) -> TrainingRun:
        config = resolve_training_preset(config_preset)
        now = datetime.now(timezone.utc)
        run = TrainingRun(
            name=name,
            dataset_slice_id=dataset_slice_id,
            config_preset=config_preset,
            config=config,
            created_at=now,
            updated_at=now,
        )
        self.store.save(run)
        self.store.write_config(run.id, {"preset": config_preset, **config})
        self.store.append_log(run.id, f"created run for slice {dataset_slice_id} preset={config_preset}")
        return run

    def execute_run(self, run_id: str) -> TrainingRun:
        run = self.get_required(run_id)
        if run.status != JobStatus.QUEUED:
            return self._finalize_run(run)

        media_ids = self._run_media_ids(run)
        try:
            finished = self.adapter.run(run_id)
        except Exception as exc:
            failed = run.model_copy(
                update={
                    "status": JobStatus.FAILED,
                    "error": str(exc)[:1200],
                    "finished_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            )
            self.store.save(failed)
            self.store.append_log(run_id, f"failed: {exc}")
            self.ingestion_service.finalize_failure(media_ids, run_id)
            return failed

        return self._finalize_run(finished)

    def _finalize_run(self, run: TrainingRun) -> TrainingRun:
        media_ids = self._run_media_ids(run)
        if run.status == JobStatus.SUCCEEDED and run.artifact_path and not run.style_version_id:
            slice_record = self.slice_service.get_required(run.dataset_slice_id)
            style = self.style_version_service.create_from_run(run, slice_record.name)
            run = run.model_copy(update={"style_version_id": style.id, "updated_at": datetime.now(timezone.utc)})
            self.store.save(run)
            self.store.append_log(run.id, f"promoted style version {style.id}")
            self.ingestion_service.finalize_success(media_ids, run.id)
        elif run.status == JobStatus.FAILED:
            self.ingestion_service.finalize_failure(media_ids, run.id)
        elif run.status == JobStatus.CANCELLED:
            self.ingestion_service.revert_ingesting(media_ids)
        return run

    def cancel_run(self, run_id: str) -> TrainingRun:
        run = self.get_required(run_id)
        if run.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
            raise ValidationAppError("Only queued or running training runs can be cancelled")

        now = datetime.now(timezone.utc)
        cancelled = run.model_copy(
            update={
                "status": JobStatus.CANCELLED,
                "finished_at": now,
                "updated_at": now,
            }
        )
        self.store.save(cancelled)
        self.store.append_log(run_id, "cancel requested")
        return self._finalize_run(cancelled)

    def read_logs(self, run_id: str, max_chars: int = 8000) -> str:
        self.get_required(run_id)
        return self.store.read_log_tail(run_id, max_chars=max_chars)

    def _run_media_ids(self, run: TrainingRun) -> list[str]:
        slice_record = self.slice_service.get_required(run.dataset_slice_id)
        return list(slice_record.frozen_media_ids or slice_record.media_ids)
