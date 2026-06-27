from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.dependencies import get_generation_service, get_job_service
from app.core.job_paths import stable_output_path
from app.domain.models import GenerationRequest, GenerationResponse
from app.services.generation_service import GenerationService
from app.services.job_service import JobService

router = APIRouter(prefix="/api", tags=["generate"])


@router.post("/generate", response_model=GenerationResponse)
def generate(
    request: GenerationRequest,
    background_tasks: BackgroundTasks,
    generation_service: GenerationService = Depends(get_generation_service),
    job_service: JobService = Depends(get_job_service),
):
    clean_request = generation_service.validate_request(request)
    job = job_service.create(clean_request)
    background_tasks.add_task(generation_service.run_job, job.id)
    return GenerationResponse(job_id=job.id, status=job.status, output_path=None)


@router.post("/jobs/{job_id}/rerun", response_model=GenerationResponse)
def rerun(
    job_id: str,
    background_tasks: BackgroundTasks,
    generation_service: GenerationService = Depends(get_generation_service),
    job_service: JobService = Depends(get_job_service),
):
    previous = job_service.get_required(job_id)
    clean_request = generation_service.validate_request(previous.request)
    job = job_service.create(clean_request)
    background_tasks.add_task(generation_service.run_job, job.id)
    return GenerationResponse(job_id=job.id, status=job.status, output_path=None)
