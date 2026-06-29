from __future__ import annotations

from pathlib import Path

from app.domain.models import JobRecord, JobStatus
from app.storage.local_file_store import LocalFileStore


def vocal_plan_file_name(job: JobRecord) -> str | None:
    if job.status != JobStatus.SUCCEEDED or not job.result:
        return None
    name = (job.result.metadata or {}).get("vocal_plan_file")
    if not name or not isinstance(name, str):
        return None
    return name


def vocal_plan_path(job: JobRecord, file_store: LocalFileStore) -> Path | None:
    file_name = vocal_plan_file_name(job)
    if not file_name:
        return None
    path = file_store.path_for_file_name(file_name)
    return path if path.exists() else None
