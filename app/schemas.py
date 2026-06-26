from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    complete = "complete"
    failed = "failed"


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=2_000)
    lyrics: str = Field(..., min_length=1, max_length=8_000)
    duration_seconds: int = Field(default=45, ge=8, le=180)
    seed: Optional[int] = Field(default=None, ge=0)

    @field_validator("prompt", "lyrics")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class GenerateResponse(BaseModel):
    job_id: str
    status: JobStatus


class GenerationMetadata(BaseModel):
    engine: str
    duration_seconds: float
    sample_rate: int
    tempo_bpm: int
    key: str
    prompt_digest: str
    warnings: list[str] = []


class JobRecord(BaseModel):
    job_id: str
    status: JobStatus
    request: GenerateRequest
    metadata: Optional[GenerationMetadata] = None
    error: Optional[str] = None
    output_path: Optional[Path] = None
