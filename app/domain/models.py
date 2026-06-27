from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


class GenerationRequest(BaseModel):
    title: str = Field(default="Untitled Sketch", min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=2000)
    lyrics: str = Field(default="", max_length=10000)
    negative_prompt: str = Field(default="", max_length=1000)

    generator: Optional[str] = Field(default=None, max_length=80)
    duration_seconds: int = Field(default=60, ge=10, le=240)
    seed: Optional[int] = Field(default=None, ge=0, le=2_147_483_647)

    mode: Literal["song", "instrumental", "vocal_demo", "loop"] = "song"
    structure: Literal["auto", "verse_chorus", "intro_verse_chorus", "hook_loop", "club_build", "ambient_loop"] = "auto"
    quality: Literal["draft", "balanced", "high"] = "draft"

    bpm: Optional[int] = Field(default=None, ge=40, le=220)
    key: Optional[str] = Field(default=None, max_length=16)
    vocal_style: Optional[str] = Field(default=None, max_length=160)
    singing_voice: Literal["auto", "female", "male", "choir", "robot", "whisper"] = "auto"
    vocal_intensity: float = Field(default=0.65, ge=0.0, le=1.0)
    genre_tags: list[str] = Field(default_factory=list, max_length=12)
    mood_tags: list[str] = Field(default_factory=list, max_length=12)

    guidance_scale: float = Field(default=7.5, ge=0.0, le=20.0)
    allow_fallback: bool = True
    include_lyrics_in_bundle: bool = True

    @field_validator("prompt", "lyrics", "title", "negative_prompt")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("key", "vocal_style")
    @classmethod
    def clean_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("genre_tags", "mood_tags")
    @classmethod
    def clean_tags(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for tag in value:
            tag = str(tag).strip().lower()[:40]
            if tag and tag not in cleaned:
                cleaned.append(tag)
        if len(cleaned) > 12:
            raise ValueError("No more than 12 tags are allowed per tag group")
        return cleaned


class GenerationResult(BaseModel):
    file_name: str
    mime_type: str = "audio/wav"
    duration_seconds: int
    sample_rate: int
    generator_name: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class JobRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    progress: float = Field(default=0, ge=0, le=1)
    message: str = "Queued"
    request: GenerationRequest
    result: Optional[GenerationResult] = None
    error: Optional[str] = None
    log_file: Optional[str] = None
    metadata_file: Optional[str] = None


class GenerationResponse(BaseModel):
    """Stable studio contract for POST /api/generate (v1)."""

    job_id: str
    status: JobStatus
    output_path: Optional[str] = None


class JobPollResponse(BaseModel):
    """Stable studio contract for GET /api/jobs/{job_id}/status (v1)."""

    job_id: str
    status: JobStatus
    output_path: Optional[str] = None


class JobStatusResponse(BaseModel):
    job: JobRecord
    download_url: Optional[str] = None
    vocal_download_url: Optional[str] = None
    bundle_url: Optional[str] = None


class GeneratorInfo(BaseModel):
    name: str
    label: str
    supports_lyrics: bool
    supports_seed: bool
    supports_duration: bool
    description: str
    backend_type: Literal["local", "adapter", "fallback"] = "local"
    available: bool = True
    status: str = "ready"
    install_hint: Optional[str] = None


class Preset(BaseModel):
    id: str
    label: str
    description: str
    prompt_suffix: str = ""
    negative_prompt: str = ""
    mode: Literal["song", "instrumental", "vocal_demo", "loop"] = "song"
    structure: Literal["auto", "verse_chorus", "intro_verse_chorus", "hook_loop", "club_build", "ambient_loop"] = "auto"
    quality: Literal["draft", "balanced", "high"] = "draft"
    duration_seconds: int = Field(default=60, ge=10, le=240)
    bpm: Optional[int] = Field(default=None, ge=40, le=220)
    key: Optional[str] = None
    vocal_style: Optional[str] = None
    singing_voice: Literal["auto", "female", "male", "choir", "robot", "whisper"] = "auto"
    vocal_intensity: float = Field(default=0.65, ge=0.0, le=1.0)
    genre_tags: list[str] = Field(default_factory=list)
    mood_tags: list[str] = Field(default_factory=list)


class ModelStatus(BaseModel):
    # --- Wiring layer: bridge is configured and paths exist ---
    ace_enabled: bool
    ace_command_configured: bool
    command_template_valid: bool
    ace_python_exists: bool
    ace_script_exists: bool
    ace_model_dir_exists: bool
    wiring_ok: bool  # True when all wiring conditions pass (fast, no subprocess)

    # --- Package / runtime layer (unchecked until POST /api/model-status/test) ---
    packages_checked: bool = False
    packages_ok: bool | None = None  # None = not yet probed
    missing_packages: list[str] = Field(default_factory=list)

    # --- CUDA (unchecked until POST /api/model-status/test) ---
    cuda_expected: bool
    cuda_available: bool | None = None  # None = not yet probed

    # --- HF cache / checkpoint storage ---
    hf_cache_dir: str = ""
    hf_cache_configured: bool = False  # HF_CACHE_DIR env var is set
    hf_cache_exists: bool = False       # configured path actually exists on disk

    # --- Fallback ---
    fallback_enabled: bool

    # --- Overall verdict ---
    can_generate: bool  # wiring-only check; does NOT require packages to be probed
    cuda_ready: bool | None = None  # None until packages probed; True when CUDA ok or not required
    first_real_generation_verified: bool = False
    first_real_generation: dict | None = None  # populated when a prior ACE external-command job exists
    user_message: str = ""  # human-readable summary of current state
    warnings: list[str] = Field(default_factory=list)

    # --- Path display (kept for compatibility) ---
    ace_python: str = ""
    ace_script: str = ""
    ace_model_dir: str = ""


class ErrorResponse(BaseModel):
    error: str
    message: str
