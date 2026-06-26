from __future__ import annotations

from pathlib import Path

from app.domain.models import JobRecord, JobStatus
from app.storage.local_file_store import LocalFileStore


def vocal_stem_file_name(job: JobRecord) -> str | None:
    if job.status != JobStatus.SUCCEEDED or not job.result:
        return None
    stem = (job.result.metadata or {}).get("vocal_stem_file")
    if not stem or not isinstance(stem, str):
        return None
    return stem


def vocal_stem_path(job: JobRecord, file_store: LocalFileStore) -> Path | None:
    stem_name = vocal_stem_file_name(job)
    if not stem_name:
        return None
    path = file_store.path_for_file_name(stem_name)
    return path if path.exists() else None
