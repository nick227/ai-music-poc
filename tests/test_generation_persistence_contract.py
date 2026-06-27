import math
import wave
from pathlib import Path

from app.core.config import Settings
from app.domain.models import GenerationRequest, GenerationResult, GeneratorInfo, JobStatus
from app.generators.registry import GeneratorRegistry
from app.services.generation_service import GenerationService
from app.services.job_service import JobService
from app.storage.local_file_store import LocalFileStore
from app.storage.local_job_store import LocalJobStore
from app.storage.local_media_store import LocalMediaStore
from app.storage.log_store import LogStore
from app.storage.metadata_store import MetadataStore
from app.services.style_version_service import StyleVersionService
from app.storage.style_version_store import StyleVersionStore


class FakeGenerator:
    name = "fake"

    def __init__(self, *, write_wav: bool = True, fail: bool = False) -> None:
        self.write_wav = write_wav
        self.fail = fail

    def info(self) -> GeneratorInfo:
        return GeneratorInfo(
            name=self.name,
            label="Fake",
            supports_lyrics=True,
            supports_seed=True,
            supports_duration=True,
            description="Fake test generator",
        )

    def generate(self, request: GenerationRequest, output_path: Path) -> GenerationResult:
        if self.fail:
            raise RuntimeError("fake adapter failed")
        if self.write_wav:
            _write_wav(output_path)
        return GenerationResult(
            file_name=output_path.name,
            duration_seconds=request.duration_seconds,
            sample_rate=44100,
            generator_name=self.name,
            metadata={"backend": "fake-backend", "engine": "fake-v1"},
        )


def _service(tmp_path: Path, fake: FakeGenerator) -> tuple[GenerationService, JobService, LocalMediaStore]:
    settings = Settings(DATA_DIR=tmp_path, DEFAULT_GENERATOR=fake.name)
    registry = GeneratorRegistry()
    registry.register(fake)
    job_service = JobService(LocalJobStore(settings.job_dir))
    media_store = LocalMediaStore(settings.media_dir)
    service = GenerationService(
        registry=registry,
        job_service=job_service,
        file_store=LocalFileStore(settings.output_dir),
        media_store=media_store,
        log_store=LogStore(settings.log_dir),
        metadata_store=MetadataStore(settings.output_dir, settings),
        style_version_service=StyleVersionService(StyleVersionStore(settings.style_versions_dir)),
        settings=settings,
    )
    return service, job_service, media_store


def _request() -> GenerationRequest:
    return GenerationRequest(
        title="Persistence Contract",
        prompt="dark piano",
        lyrics="one two",
        generator="fake",
        duration_seconds=10,
        seed=123,
    )


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 44100
    duration_seconds = 1
    frames = bytearray()
    for index in range(sample_rate * duration_seconds):
        sample = int(math.sin(index / 12.0) * 12000)
        frames.extend(sample.to_bytes(2, "little", signed=True))
        frames.extend(sample.to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(frames))


def test_generation_success_creates_media_asset_after_wav_verified(tmp_path):
    service, job_service, media_store = _service(tmp_path, FakeGenerator())
    job = job_service.create(_request())

    service.run_job(job.id)

    saved = job_service.get_required(job.id)
    assert saved.status == JobStatus.SUCCEEDED
    assert saved.media_asset_id == f"media_{job.id}"
    assert saved.version_details["backend"] == "fake-backend"
    assert saved.version_details["modelVersion"] == "fake-v1"

    media = media_store.get(saved.media_asset_id)
    assert media is not None
    assert media.kind == "GENERATED_SONG"
    assert media.source == "GENERATION"
    assert media.file_path == f"outputs/{job.id}.wav"
    assert media.generation_id == job.id
    assert media.version_details["seed"] == 123
    assert media.sample_rate == 44100


def test_generation_failure_keeps_generation_record_without_media_asset(tmp_path):
    service, job_service, media_store = _service(tmp_path, FakeGenerator(fail=True))
    job = job_service.create(_request())

    service.run_job(job.id)

    saved = job_service.get_required(job.id)
    assert saved.status == JobStatus.FAILED
    assert saved.error == "fake adapter failed"
    assert saved.media_asset_id is None
    assert saved.version_details["prompt"] == "dark piano"
    assert media_store.list_recent() == []


def test_missing_wav_fails_without_creating_media_asset(tmp_path):
    service, job_service, media_store = _service(tmp_path, FakeGenerator(write_wav=False))
    job = job_service.create(_request())

    service.run_job(job.id)

    saved = job_service.get_required(job.id)
    assert saved.status == JobStatus.FAILED
    assert "Expected audio output was not created" in saved.error
    assert saved.media_asset_id is None
    assert media_store.list_recent() == []
