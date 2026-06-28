from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import StyleVersionStatus


class StyleVersion(BaseModel):
    id: str = Field(default_factory=lambda: f"style_{uuid4().hex}")
    name: str
    training_run_id: str
    dataset_slice_id: str
    artifact_path: str
    backend: str = "MOCK"
    base_model_id: str = "acestep-v15-turbo"
    base_model_name: str = "ACE-Step v1.5 Turbo"
    training_mode: str = "lora"
    artifact_type: str = "lora"
    status: StyleVersionStatus = StyleVersionStatus.ACTIVE
    parent_lora_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be empty")
        return value
