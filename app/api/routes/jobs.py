from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_file_store, get_job_service, get_log_store
from app.core.vocal_assets import vocal_stem_path
from app.core.vocal_plan_assets import vocal_plan_path
from app.core.job_paths import stable_output_path
from app.domain.models import JobPollResponse, JobStatus, JobStatusResponse
from app.services.job_service import JobService
from app.storage.local_file_store import LocalFileStore
from app.storage.log_store import LogStore

router = APIRouter(prefix="/api", tags=["jobs"])


def _job_poll(job) -> JobPollResponse:
    return JobPollResponse(
        job_id=job.id,
        status=job.status,
        output_path=stable_output_path(job),
    )


def _job_urls(job, file_store: LocalFileStore) -> JobStatusResponse:
    ready = job.status == JobStatus.SUCCEEDED and job.result
    vocal_ready = ready and vocal_stem_path(job, file_store) is not None
    vocal_plan_ready = ready and vocal_plan_path(job, file_store) is not None
    return JobStatusResponse(
        job=job,
        download_url=f"/api/download/{job.id}" if ready else None,
        vocal_download_url=f"/api/download/{job.id}/vocal" if vocal_ready else None,
        vocal_plan_url=f"/api/download/{job.id}/vocal-plan" if vocal_plan_ready else None,
        bundle_url=f"/api/download/{job.id}/bundle" if ready else None,
    )


@router.get("/jobs/{job_id}/status", response_model=JobPollResponse)
def get_job_status(job_id: str, job_service: JobService = Depends(get_job_service)):
    job = job_service.get_required(job_id)
    return _job_poll(job)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str, job_service: JobService = Depends(get_job_service), file_store: LocalFileStore = Depends(get_file_store)):
    job = job_service.get_required(job_id)
    return _job_urls(job, file_store)


@router.get("/jobs/{job_id}/log")
def get_job_log(job_id: str, job_service: JobService = Depends(get_job_service), log_store: LogStore = Depends(get_log_store)):
    job_service.get_required(job_id)
    return {"job_id": job_id, "log": log_store.tail(job_id)}


@router.get("/jobs")
def list_jobs(limit: int = Query(default=25, ge=1, le=100), job_service: JobService = Depends(get_job_service)):
    jobs = job_service.list_recent(limit=limit)
    return {"jobs": jobs}
