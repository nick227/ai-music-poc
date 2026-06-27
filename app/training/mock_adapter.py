from __future__ import annotations

import json
import time
from pathlib import Path

from app.domain.models import JobStatus
from app.domain.training import TrainingRun
from app.storage.training_run_store import TrainingRunStore


class MockTrainingAdapter:
    name = "mock-training"

    def __init__(self, store: TrainingRunStore, step_delay_seconds: float = 0.05) -> None:
        self.store = store
        self.step_delay_seconds = step_delay_seconds

    def run(self, run_id: str) -> TrainingRun:
        run = self.store.get(run_id)
        if run is None:
            raise RuntimeError(f"Training run not found: {run_id}")

        self._transition(run_id, JobStatus.RUNNING, "Training started (mock adapter)")
        self.store.append_log(run_id, "mock adapter: queued complete")
        time.sleep(self.step_delay_seconds)

        if self._is_cancelled(run_id):
            return self._mark_cancelled(run_id)

        self.store.append_log(run_id, "mock adapter: running epoch 1/1")
        time.sleep(self.step_delay_seconds)

        if self._is_cancelled(run_id):
            return self._mark_cancelled(run_id)

        artifact_path = self._write_artifact(run_id)
        self.store.append_log(run_id, f"mock adapter: wrote artifact {artifact_path.name}")

        updated = self.store.get(run_id)
        if updated is None:
            raise RuntimeError(f"Training run not found: {run_id}")
        finished = updated.model_copy(
            update={
                "status": JobStatus.SUCCEEDED,
                "artifact_path": f"training_runs/{run_id}/artifacts/{artifact_path.name}",
                "finished_at": self._now(),
                "updated_at": self._now(),
            }
        )
        self.store.save(finished)
        self.store.append_log(run_id, "mock adapter: succeeded")
        return finished

    def _write_artifact(self, run_id: str) -> Path:
        run = self.store.get(run_id)
        if run is None:
            raise RuntimeError(f"Training run not found: {run_id}")
        artifact_dir = self.store.artifacts_dir(run_id)
        path = artifact_dir / "lora.mock.json"
        payload = {
            "format": "mock-lora",
            "training_run_id": run_id,
            "dataset_slice_id": run.dataset_slice_id,
            "config_preset": run.config_preset,
            "config": run.config,
            "backend": run.backend,
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def _transition(self, run_id: str, status: JobStatus, message: str) -> None:
        run = self.store.get(run_id)
        if run is None:
            raise RuntimeError(f"Training run not found: {run_id}")
        now = self._now()
        updates: dict = {"status": status, "updated_at": now, "error": None}
        if status == JobStatus.RUNNING:
            updates["started_at"] = now
        self.store.save(run.model_copy(update=updates))
        self.store.append_log(run_id, message)

    def _is_cancelled(self, run_id: str) -> bool:
        run = self.store.get(run_id)
        return run is not None and run.status == JobStatus.CANCELLED

    def _mark_cancelled(self, run_id: str) -> TrainingRun:
        run = self.store.get(run_id)
        if run is None:
            raise RuntimeError(f"Training run not found: {run_id}")
        now = self._now()
        finished = run.model_copy(update={"finished_at": now, "updated_at": now})
        self.store.save(finished)
        self.store.append_log(run_id, "mock adapter: cancelled")
        return finished

    @staticmethod
    def _now():
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)
