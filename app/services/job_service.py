from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

from app.core.errors import NotFoundError
from app.domain.models import GenerationRequest, GenerationResult, JobRecord, JobStatus, MediaAsset
from app.storage.local_job_store import LocalJobStore


class JobService:
    def __init__(self, store: LocalJobStore) -> None:
        self.store = store

    def create(self, request: GenerationRequest) -> JobRecord:
        job = JobRecord(request=request)
        self.store.save(job)
        return job

    def get_required(self, job_id: str) -> JobRecord:
        job = self.store.get(job_id)
        if not job:
            raise NotFoundError("Job not found")
        return job

    def get(self, job_id: str) -> JobRecord | None:
        return self.store.get(job_id)

    def list_recent(self, limit: int = 25) -> List[JobRecord]:
        return self.store.list_recent(limit=limit)

    def mark_running(self, job: JobRecord) -> JobRecord:
        job.status = JobStatus.RUNNING
        job.started_at = datetime.now(timezone.utc)
        job.progress = 0.2
        job.message = "Generating audio"
        self.store.save(job)
        return job

    def store_version_details(self, job: JobRecord, version_details: dict[str, Any]) -> JobRecord:
        job.version_details = version_details
        self.store.save(job)
        return job

    def mark_succeeded(self, job: JobRecord, result: GenerationResult, media_asset: MediaAsset, version_details: dict[str, Any], metadata_file: str | None = None, log_file: str | None = None) -> JobRecord:
        job.status = JobStatus.SUCCEEDED
        job.finished_at = datetime.now(timezone.utc)
        job.progress = 1.0
        job.message = "Complete"
        job.result = result
        job.media_asset_id = media_asset.id
        job.version_details = version_details
        job.metadata_file = metadata_file
        job.log_file = log_file
        self.store.save(job)
        return job

    def mark_failed(self, job: JobRecord, error: str, log_file: str | None = None) -> JobRecord:
        job.status = JobStatus.FAILED
        job.finished_at = datetime.now(timezone.utc)
        job.progress = 1.0
        job.message = "Failed"
        job.error = error
        job.log_file = log_file
        self.store.save(job)
        return job

    def mark_timeout(self, job: JobRecord, error: str, log_file: str | None = None) -> JobRecord:
        job.status = JobStatus.TIMEOUT
        job.finished_at = datetime.now(timezone.utc)
        job.progress = 1.0
        job.message = "Timed out"
        job.error = error
        job.log_file = log_file
        self.store.save(job)
        return job
