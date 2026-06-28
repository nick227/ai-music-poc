from __future__ import annotations

from datetime import datetime, timezone

from app.core.errors import NotFoundError, ValidationAppError
from app.core.config import Settings
from app.domain.enums import DatasetSliceStatus, StyleVersionStatus
from app.domain.models import JobStatus
from app.domain.training import TrainingRun
from app.domain.training_presets import TRAINING_PRESETS, resolve_training_preset
from app.domain.slices import DatasetSlice
from app.domain.training_status import describe_pipeline, describe_run, is_dry_run_backend, is_mock_backend, is_real_ace_backend
from app.services.ingestion_service import IngestionService
from app.services.ready_audio_service import ReadyAudioService
from app.services.slice_service import SliceService
from app.services.style_version_service import StyleVersionService
from app.storage.training_run_store import TrainingRunStore
from app.training.adapter import TrainingAdapter, TrainingAdapterResult, TrainingRequest
from app.core.ace_runtime import load_runtime_profile, AceRuntimeStatus


class TrainingService:
    def __init__(
        self,
        store: TrainingRunStore,
        slice_service: SliceService,
        adapter: TrainingAdapter,
        ingestion_service: IngestionService,
        ready_audio_service: ReadyAudioService,
        style_version_service: StyleVersionService,
        settings: Settings,
    ) -> None:
        self.store = store
        self.slice_service = slice_service
        self.adapter = adapter
        self.ingestion_service = ingestion_service
        self.ready_audio_service = ready_audio_service
        self.style_version_service = style_version_service
        self.settings = settings

    def list_runs(self) -> list[TrainingRun]:
        return self.store.list_all()

    def pipeline_status(self) -> dict:
        return describe_pipeline(self.settings, self.adapter.name)

    def run_status(self, run: TrainingRun) -> dict:
        return describe_run(run, self.settings)

    def get_required(self, run_id: str) -> TrainingRun:
        run = self.store.get(run_id)
        if run is None:
            raise NotFoundError(f"Training run not found: {run_id}")
        return run

    def list_ready_audio(self, concept_id: str | None = None) -> dict:
        return self.ready_audio_service.list_ready(concept_id)

    def list_packages(self) -> list[DatasetSlice]:
        return [
            item
            for item in self.slice_service.list_slices()
            if item.status == DatasetSliceStatus.READY and item.frozen_media_ids
        ]

    def create_package(
        self,
        concept_id: str | None = None,
        media_ids: list[str] | None = None,
        name: str | None = None,
        start_training: bool = True,
        config_preset: str = "calibration",
        confirm_real_training: bool = False,
    ) -> tuple[DatasetSlice, TrainingRun | None]:
        if config_preset not in TRAINING_PRESETS:
            raise ValidationAppError(f"Unknown config preset: {config_preset}")

        resolved_ids = self.ready_audio_service.resolve_for_package(concept_id, media_ids)
        package_name = (
            name or f"Training package ({len(resolved_ids)} track{'s' if len(resolved_ids) != 1 else ''})"
        ).strip()
        frozen_slice = self.slice_service.create_and_freeze(package_name, resolved_ids)

        if not start_training:
            return frozen_slice, None

        if not self.settings.training_enabled:
            raise ValidationAppError("Training is disabled")
        if self.store.find_active_run() is not None:
            raise ValidationAppError("Another training run is already active")

        run = self._create_run_record(
            package_name,
            frozen_slice.id,
            config_preset,
            confirm_real_training=confirm_real_training,
        )
        self.ingestion_service.mark_ingesting(resolved_ids, run.id)
        return frozen_slice, run

    def ingest(
        self,
        media_ids: list[str] | None = None,
        name: str | None = None,
        config_preset: str = "calibration",
        concept_id: str | None = None,
    ) -> TrainingRun:
        _, run = self.create_package(
            concept_id=concept_id,
            media_ids=media_ids,
            name=name,
            start_training=True,
            config_preset=config_preset,
        )
        if run is None:
            raise ValidationAppError("Training is disabled")
        return run

    def create_run(
        self,
        name: str,
        dataset_slice_id: str,
        config_preset: str,
        confirm_real_training: bool = False,
    ) -> TrainingRun:
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

        return self._create_run_record(
            clean_name,
            dataset_slice_id,
            config_preset,
            confirm_real_training=confirm_real_training,
        )

    def _create_run_record(
        self,
        name: str,
        dataset_slice_id: str,
        config_preset: str,
        *,
        confirm_real_training: bool = False,
    ) -> TrainingRun:
        config = resolve_training_preset(config_preset)
        if confirm_real_training:
            config["confirm_real_training"] = True

        ace_cfg = {}
        profile_data = load_runtime_profile(self.settings.data_dir)
        if profile_data:
            try:
                status = AceRuntimeStatus.model_validate(profile_data)
                if status.hardware and status.hardware.safe_recommended_config:
                    ace_cfg = status.hardware.safe_recommended_config.model_dump()
            except Exception:
                pass
        
        if ace_cfg:
            config["runtime"] = ace_cfg
            config["device"] = ace_cfg.get("device")
            config["batch_size"] = ace_cfg.get("batch_size")

        now = datetime.now(timezone.utc)
        run = TrainingRun(
            name=name,
            dataset_slice_id=dataset_slice_id,
            backend=self.adapter.name,
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
            training_request = self._training_request(run)
            result = self.adapter.run(training_request)
            finished = result.run if isinstance(result, TrainingAdapterResult) else result
            self.store.save(finished)
            if isinstance(result, TrainingAdapterResult) and result.dry_run:
                self.store.append_log(run_id, "ACE command rendered; subprocess not started")
            elif isinstance(result, TrainingAdapterResult) and result.command:
                self.store.append_log(run_id, f"command: {' '.join(result.command)}")
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
            if is_mock_backend(run.backend):
                slice_record = self.slice_service.get_required(run.dataset_slice_id)
                style = self.style_version_service.create_from_run(run, slice_record.name)
                run = run.model_copy(update={"style_version_id": style.id, "updated_at": datetime.now(timezone.utc)})
                self.store.save(run)
                self.store.append_log(run.id, f"mock artifact produced; promoted style version {style.id}")
                self.ingestion_service.finalize_success(media_ids, run.id)
            elif is_real_ace_backend(run.backend):
                slice_record = self.slice_service.get_required(run.dataset_slice_id)
                style = self.style_version_service.create_from_run(
                    run,
                    slice_record.name,
                    status=StyleVersionStatus.CANDIDATE,
                )
                run = run.model_copy(update={"style_version_id": style.id, "updated_at": datetime.now(timezone.utc)})
                self.store.save(run)
                self.store.append_log(run.id, f"ACE adapter artifact produced; candidate style version {style.id}")
                self.ingestion_service.finalize_success(media_ids, run.id)
        elif run.status == JobStatus.SUCCEEDED and is_dry_run_backend(run.backend):
            self.store.append_log(run.id, "dry run complete; ready audio unchanged")
            self.ingestion_service.revert_ingesting(media_ids)
        elif run.status == JobStatus.SUCCEEDED and not run.artifact_path:
            self.ingestion_service.revert_ingesting(media_ids)
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

    def _training_request(self, run: TrainingRun) -> TrainingRequest:
        package_path = self.slice_service.build_package_path(run.dataset_slice_id)
        run_dir = self.store.run_dir(run.id)
        return TrainingRequest(
            run=run,
            package_path=package_path,
            run_dir=run_dir,
            config_path=run_dir / "config.json",
            log_path=self.store.log_path(run.id),
            artifacts_dir=self.store.artifacts_dir(run.id),
        )
