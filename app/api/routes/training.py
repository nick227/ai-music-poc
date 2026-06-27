from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.api.dependencies import get_training_service
from app.api.schemas.ingestion_api import IngestRequest, IngestResponse, ingest_response
from app.api.schemas.training_api import (
    TrainingPipelineStatusResponse,
    TrainingRunCreateRequest,
    TrainingRunListResponse,
    TrainingRunLogsResponse,
    TrainingRunResponse,
    training_run_to_response,
)
from app.api.schemas.training_package_api import (
    CreatePackageRequest,
    CreatePackageResponse,
    ReadyAudioResponse,
    TrainingPackageListResponse,
    create_package_response,
    package_to_response,
)
from app.core.config import Settings, get_settings
from app.services.training_service import TrainingService

router = APIRouter(prefix="/api/training", tags=["training"])


@router.get("/pipeline-status", response_model=TrainingPipelineStatusResponse)
def get_training_pipeline_status(
    training_service: TrainingService = Depends(get_training_service),
):
    return TrainingPipelineStatusResponse.model_validate(training_service.pipeline_status())


@router.get("/ready-audio", response_model=ReadyAudioResponse)
def get_ready_audio(
    concept_id: str | None = Query(default=None),
    training_service: TrainingService = Depends(get_training_service),
):
    return ReadyAudioResponse.model_validate(training_service.list_ready_audio(concept_id))


@router.get("/packages", response_model=TrainingPackageListResponse)
def list_training_packages(training_service: TrainingService = Depends(get_training_service)):
    packages = [package_to_response(item) for item in training_service.list_packages()]
    packages.sort(key=lambda item: item.updated_at, reverse=True)
    return TrainingPackageListResponse(packages=packages)


@router.post("/packages", response_model=CreatePackageResponse)
def create_training_package(
    request: CreatePackageRequest,
    background_tasks: BackgroundTasks,
    training_service: TrainingService = Depends(get_training_service),
    settings: Settings = Depends(get_settings),
):
    media_ids = request.media_ids or None
    package, run = training_service.create_package(
        concept_id=request.concept_id,
        media_ids=media_ids,
        name=request.name,
        start_training=request.start_training,
        config_preset=request.config_preset,
    )
    if run is not None:
        background_tasks.add_task(training_service.execute_run, run.id)
    return create_package_response(package, run, settings)


@router.post("/ingest", response_model=IngestResponse)
def ingest_training_queue(
    request: IngestRequest,
    background_tasks: BackgroundTasks,
    training_service: TrainingService = Depends(get_training_service),
    settings: Settings = Depends(get_settings),
):
    media_ids = request.media_ids or None
    run = training_service.ingest(
        media_ids=media_ids,
        name=request.name,
        config_preset=request.config_preset,
        concept_id=request.concept_id,
    )
    background_tasks.add_task(training_service.execute_run, run.id)
    return ingest_response(run, settings)


@router.get("/runs", response_model=TrainingRunListResponse)
def list_training_runs(
    training_service: TrainingService = Depends(get_training_service),
    settings: Settings = Depends(get_settings),
):
    runs = [training_run_to_response(item, settings) for item in training_service.list_runs()]
    return TrainingRunListResponse(runs=runs)


@router.post("/runs", response_model=TrainingRunResponse)
def create_training_run(
    request: TrainingRunCreateRequest,
    background_tasks: BackgroundTasks,
    training_service: TrainingService = Depends(get_training_service),
    settings: Settings = Depends(get_settings),
):
    run = training_service.create_run(
        name=request.name,
        dataset_slice_id=request.dataset_slice_id,
        config_preset=request.config_preset,
    )
    background_tasks.add_task(training_service.execute_run, run.id)
    return training_run_to_response(run, settings)


@router.get("/runs/{run_id}", response_model=TrainingRunResponse)
def get_training_run(
    run_id: str,
    training_service: TrainingService = Depends(get_training_service),
    settings: Settings = Depends(get_settings),
):
    return training_run_to_response(training_service.get_required(run_id), settings)


@router.post("/runs/{run_id}/cancel", response_model=TrainingRunResponse)
def cancel_training_run(
    run_id: str,
    training_service: TrainingService = Depends(get_training_service),
    settings: Settings = Depends(get_settings),
):
    return training_run_to_response(training_service.cancel_run(run_id), settings)


@router.get("/runs/{run_id}/logs", response_model=TrainingRunLogsResponse)
def get_training_run_logs(
    run_id: str,
    max_chars: int = Query(default=8000, ge=100, le=50000),
    training_service: TrainingService = Depends(get_training_service),
):
    log = training_service.read_logs(run_id, max_chars=max_chars)
    return TrainingRunLogsResponse(run_id=run_id, log=log)
