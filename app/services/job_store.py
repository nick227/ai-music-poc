from __future__ import annotations

import threading
import traceback
import uuid
from pathlib import Path

from app.schemas import GenerateRequest, GenerateResponse, JobRecord, JobStatus
from app.services.generator_factory import create_generator


class JobStore:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}
        self._generator = create_generator()

    def create_job(self, request: GenerateRequest) -> GenerateResponse:
        job_id = uuid.uuid4().hex
        record = JobRecord(job_id=job_id, status=JobStatus.queued, request=request)
        with self._lock:
            self._jobs[job_id] = record
        thread = threading.Thread(target=self._run_job, args=(job_id,), daemon=True)
        thread.start()
        return GenerateResponse(job_id=job_id, status=JobStatus.queued)

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _set_job(self, job_id: str, **updates: object) -> None:
        with self._lock:
            current = self._jobs[job_id]
            self._jobs[job_id] = current.model_copy(update=updates)

    def _run_job(self, job_id: str) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        self._set_job(job_id, status=JobStatus.running)
        output_path = self.output_dir / f"{job_id}.wav"
        try:
            metadata = self._generator.generate(job.request, output_path)
            self._set_job(job_id, status=JobStatus.complete, metadata=metadata, output_path=output_path)
        except Exception as exc:  # pragma: no cover
            print(traceback.format_exc())
            self._set_job(job_id, status=JobStatus.failed, error=str(exc))
