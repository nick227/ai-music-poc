from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.domain.style_versions import StyleVersion
from app.domain.training import TrainingRun
from app.api.schemas.training_api import TrainingRunResponse, training_run_to_response


class IngestionQueueItem(BaseModel):
    id: str
    title: str
    duration_seconds: Optional[float] = None
    category_count: int
    ingestion_status: str
    review_status: str
    rights_status: str
    last_training_run_id: Optional[str] = None
    ingested_at: Optional[str] = None
    updated_at: str


class IngestionQueueResponse(BaseModel):
    queue: list[IngestionQueueItem]
    ingested: list[IngestionQueueItem]


class IngestRequest(BaseModel):
    media_ids: list[str] = Field(default_factory=list)
    concept_id: Optional[str] = None
    name: Optional[str] = Field(default=None, max_length=160)
    config_preset: str = Field(default="calibration", max_length=40)


class IngestResponse(BaseModel):
    run: TrainingRunResponse


def ingest_response(run: TrainingRun, settings=None) -> IngestResponse:
    from app.core.config import Settings

    return IngestResponse(run=training_run_to_response(run, settings or Settings()))
