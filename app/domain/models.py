from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import IngestionStatus, ReviewDecision


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"


class MediaKind(str, Enum):
    REFERENCE = "REFERENCE"
    UPLOAD = "UPLOAD"
    GENERATED_SONG = "GENERATED_SONG"
    CLIP = "CLIP"
    STEM = "STEM"
    NOTE_ONLY = "NOTE_ONLY"


class MediaSource(str, Enum):
    USER_IMPORT = "USER_IMPORT"
    GENERATION = "GENERATION"
    MANUAL_REFERENCE = "MANUAL_REFERENCE"


class ReviewStatus(str, Enum):
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REVIEWED = "REVIEWED"
    REJECTED = "REJECTED"


class RightsStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    CONFIRMED = "CONFIRMED"
    DO_NOT_TRAIN = "DO_NOT_TRAIN"


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
    style_version_id: Optional[str] = Field(default=None, max_length=80)
    lora_path: Optional[str] = Field(default=None, max_length=1000)
    lora_scale: float = Field(default=1.0, ge=0.0, le=2.0)

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
    media_asset_id: Optional[str] = None
    version_details: Dict[str, Any] = Field(default_factory=dict)


class MediaAsset(BaseModel):
    id: str = Field(default_factory=lambda: f"media_{uuid4().hex}")
    title: str
    kind: MediaKind
    source: MediaSource
    file_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    review_status: ReviewStatus = ReviewStatus.NEEDS_REVIEW
    rights_status: RightsStatus = RightsStatus.UNKNOWN
    review_decision: Optional[ReviewDecision] = None
    review_score: Optional[int] = Field(default=None, ge=1, le=5)
    review_notes: Optional[str] = None
    generation_id: Optional[str] = None
    version_details: Dict[str, Any] = Field(default_factory=dict)
    ingestion_status: IngestionStatus = IngestionStatus.PENDING
    last_training_run_id: Optional[str] = None
    ingested_at: Optional[datetime] = None
    ingested_fingerprint: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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


class SongGenerationSummary(BaseModel):
    id: str
    status: JobStatus
    output_path: Optional[str] = None
    prompt: str
    lyrics: str = ""
    seed: Optional[int] = None
    backend: Optional[str] = None
    model_version: Optional[str] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


class SongResponse(BaseModel):
    id: str
    title: str
    media_asset_id: str
    kind: MediaKind
    file_path: Optional[str] = None
    audio_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    review_status: ReviewStatus
    review_decision: Optional[ReviewDecision] = None
    review_score: Optional[int] = None
    review_notes: Optional[str] = None
    generation_id: Optional[str] = None
    version_details: Dict[str, Any] = Field(default_factory=dict)
    generation: Optional[SongGenerationSummary] = None
    created_at: datetime
    updated_at: datetime


class SongReviewRequest(BaseModel):
    decision: ReviewDecision
    overall_score: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = None

    @field_validator("notes")
    @classmethod
    def strip_notes(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        return value or None


class SongListResponse(BaseModel):
    songs: list[SongResponse]


class SongCompareSharedSettings(BaseModel):
    prompt: Optional[str] = None
    seed: Optional[int] = None
    duration_seconds: Optional[int] = None
    mode: Optional[str] = None
    quality: Optional[str] = None
    generator: Optional[str] = None


class SongCompareResponse(BaseModel):
    baseline: SongResponse
    styled: SongResponse
    shared: SongCompareSharedSettings
    style_version_id: Optional[str] = None
    training_run_id: Optional[str] = None


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
