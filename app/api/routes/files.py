from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.api.dependencies import get_bundle_service, get_file_store, get_job_service
from app.core.errors import NotFoundError
from app.core.vocal_assets import vocal_stem_path
from app.domain.models import JobStatus
from app.services.bundle_service import BundleService
from app.services.job_service import JobService
from app.storage.local_file_store import LocalFileStore

router = APIRouter(prefix="/api", tags=["files"])


def _safe_title(title: str, fallback: str) -> str:
    return "".join(ch for ch in title if ch.isalnum() or ch in (" ", "-", "_")).strip() or fallback


@router.get("/download/{job_id}")
def download(job_id: str, job_service: JobService = Depends(get_job_service), file_store: LocalFileStore = Depends(get_file_store)):
    job = job_service.get_required(job_id)
    if job.status != JobStatus.SUCCEEDED or not job.result:
        raise NotFoundError("Generated file is not available")
    path = file_store.path_for_file_name(job.result.file_name)
    if not path.exists():
        raise NotFoundError("Generated file is missing")
    return FileResponse(path, media_type=job.result.mime_type, filename=f"{_safe_title(job.request.title, job.id)}.wav")


@router.get("/download/{job_id}/vocal")
def download_vocal(job_id: str, job_service: JobService = Depends(get_job_service), file_store: LocalFileStore = Depends(get_file_store)):
    job = job_service.get_required(job_id)
    if job.status != JobStatus.SUCCEEDED or not job.result:
        raise NotFoundError("Vocal stem is not available")
    path = vocal_stem_path(job, file_store)
    if not path:
        raise NotFoundError("Vocal stem was not generated for this job")
    return FileResponse(path, media_type="audio/wav", filename=f"{_safe_title(job.request.title, job.id)}-vocal.wav")


@router.get("/download/{job_id}/bundle")
def download_bundle(job_id: str, job_service: JobService = Depends(get_job_service), bundle_service: BundleService = Depends(get_bundle_service)):
    job = job_service.get_required(job_id)
    if job.status != JobStatus.SUCCEEDED or not job.result:
        raise NotFoundError("Generated bundle is not available")
    path = bundle_service.create_bundle(job)
    return FileResponse(path, media_type="application/zip", filename=f"{_safe_title(job.request.title, job.id)}-bundle.zip")
