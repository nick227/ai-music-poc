from __future__ import annotations

from app.domain.models import JobRecord, JobStatus


def stable_output_path(job: JobRecord) -> str | None:
    """Stable relative path under DATA_DIR, e.g. outputs/{job_id}.wav."""
    if job.status != JobStatus.SUCCEEDED or not job.result:
        return None
    return f"outputs/{job.result.file_name}"
