from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.api.dependencies import get_training_service
from app.api.schemas.training_api import (
    TrainingRunCreateRequest,
    TrainingRunListResponse,
    TrainingRunLogsResponse,
    TrainingRunResponse,
    training_run_to_response,
)
from app.services.training_service import TrainingService

router = APIRouter(prefix="/api/training", tags=["training"])


@router.get("/runs", response_model=TrainingRunListResponse)
def list_training_runs(training_service: TrainingService = Depends(get_training_service)):
    runs = [training_run_to_response(item) for item in training_service.list_runs()]
    return TrainingRunListResponse(runs=runs)


@router.post("/runs", response_model=TrainingRunResponse)
def create_training_run(
    request: TrainingRunCreateRequest,
    background_tasks: BackgroundTasks,
    training_service: TrainingService = Depends(get_training_service),
):
    run = training_service.create_run(
        name=request.name,
        dataset_slice_id=request.dataset_slice_id,
        config_preset=request.config_preset,
    )
    background_tasks.add_task(training_service.execute_run, run.id)
    return training_run_to_response(run)


@router.get("/runs/{run_id}", response_model=TrainingRunResponse)
def get_training_run(
    run_id: str,
    training_service: TrainingService = Depends(get_training_service),
):
    return training_run_to_response(training_service.get_required(run_id))


@router.post("/runs/{run_id}/cancel", response_model=TrainingRunResponse)
def cancel_training_run(
    run_id: str,
    training_service: TrainingService = Depends(get_training_service),
):
    return training_run_to_response(training_service.cancel_run(run_id))


@router.get("/runs/{run_id}/logs", response_model=TrainingRunLogsResponse)
def get_training_run_logs(
    run_id: str,
    max_chars: int = Query(default=8000, ge=100, le=50000),
    training_service: TrainingService = Depends(get_training_service),
):
    log = training_service.read_logs(run_id, max_chars=max_chars)
    return TrainingRunLogsResponse(run_id=run_id, log=log)
