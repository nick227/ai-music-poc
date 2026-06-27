from __future__ import annotations

import logging
import subprocess
from typing import Any

from app.core.audio_validation import validate_wav_output
from app.core.config import Settings
from app.core.errors import ValidationAppError
from app.domain.enums import StyleVersionStatus
from app.domain.models import GenerationRequest, GenerationResult, MediaAsset, MediaKind, MediaSource
from app.generators.registry import GeneratorRegistry
from app.services.job_service import JobService
from app.services.style_version_service import StyleVersionService
from app.storage.local_file_store import LocalFileStore
from app.storage.local_media_store import LocalMediaStore
from app.storage.log_store import LogStore
from app.storage.metadata_store import MetadataStore

logger = logging.getLogger(__name__)


class GenerationService:
    def __init__(
        self,
        registry: GeneratorRegistry,
        job_service: JobService,
        file_store: LocalFileStore,
        media_store: LocalMediaStore,
        log_store: LogStore,
        metadata_store: MetadataStore,
        style_version_service: StyleVersionService,
        settings: Settings,
    ) -> None:
        self.registry = registry
        self.job_service = job_service
        self.file_store = file_store
        self.media_store = media_store
        self.log_store = log_store
        self.metadata_store = metadata_store
        self.style_version_service = style_version_service
        self.settings = settings

    def validate_request(self, request: GenerationRequest) -> GenerationRequest:
        generator_name = request.generator or self.settings.default_generator
        if generator_name not in self.registry.names():
            raise ValidationAppError(f"Unknown generator: {generator_name}")
        if request.style_version_id:
            style = self.style_version_service.get_required(request.style_version_id)
            if style.status != StyleVersionStatus.ACTIVE:
                raise ValidationAppError("Style version is not active")
        data = request.model_dump()
        data["generator"] = generator_name
        return GenerationRequest.model_validate(data)

    def run_job(self, job_id: str) -> None:
        job = self.job_service.get_required(job_id)
        log_path = self.log_store.path_for_job(job.id)
        self.log_store.append(job.id, f"job created title={job.request.title!r} generator={job.request.generator}")
        self.job_service.mark_running(job)
        generator_name = job.request.generator or self.settings.default_generator
        version_details = self._request_version_details(job.id, job.request, generator_name)
        self.job_service.store_version_details(job, version_details)
        try:
            generator = self.registry.get(generator_name)
            output_path = self.file_store.output_path_for_job(job.id)
            self.log_store.append(job.id, f"running generator={generator_name} output={output_path}")
            result = generator.generate(job.request, output_path)
            audio = validate_wav_output(output_path, expected_duration_seconds=job.request.duration_seconds)
            version_details = self._result_version_details(version_details, result)
            media_asset = MediaAsset(
                id=f"media_{job.id}",
                title=job.request.title,
                kind=MediaKind.GENERATED_SONG,
                source=MediaSource.GENERATION,
                file_path=f"outputs/{result.file_name}",
                duration_seconds=audio.duration_seconds,
                sample_rate=audio.sample_rate,
                channels=audio.channels,
                generation_id=job.id,
                version_details=version_details,
            )
            self.media_store.save(media_asset)
            self.job_service.store_version_details(job, version_details)
            metadata_path = self.metadata_store.write(job, result)
            self.log_store.append(job.id, f"succeeded file={result.file_name} media={media_asset.id} metadata={metadata_path.name}")
            self.job_service.mark_succeeded(job, result, media_asset=media_asset, version_details=version_details, metadata_file=metadata_path.name, log_file=log_path.name)
        except subprocess.TimeoutExpired as exc:
            logger.exception("job_timeout job_id=%s", job.id)
            message = f"Generation timed out after {exc.timeout} seconds"
            self.log_store.append(job.id, message)
            self.job_service.mark_timeout(job, message, log_file=log_path.name)
        except Exception as exc:
            logger.exception("job_failed job_id=%s", job.id)
            message = str(exc)[:1200]
            self.log_store.append(job.id, f"failed error={message}")
            self.job_service.mark_failed(job, message, log_file=log_path.name)

    def _request_version_details(self, generation_id: str, request: GenerationRequest, generator_name: str) -> dict[str, Any]:
        style_version_id = None
        training_run_id = None
        dataset_slice_id = None
        model_artifact_id = None
        if request.style_version_id:
            style = self.style_version_service.get_required(request.style_version_id)
            style_version_id = style.id
            training_run_id = style.training_run_id
            dataset_slice_id = style.dataset_slice_id
            model_artifact_id = style.artifact_path

        return {
            "generationId": generation_id,
            "backend": generator_name,
            "modelVersion": None,
            "styleVersionId": style_version_id,
            "trainingRunId": training_run_id,
            "datasetSliceId": dataset_slice_id,
            "modelArtifactId": model_artifact_id,
            "targetConceptId": None,
            "targetCategoryIds": [],
            "prompt": request.prompt,
            "lyrics": request.lyrics,
            "negativePrompt": request.negative_prompt,
            "seed": request.seed,
            "durationSeconds": request.duration_seconds,
            "settings": {
                "mode": request.mode,
                "structure": request.structure,
                "quality": request.quality,
                "bpm": request.bpm,
                "key": request.key,
                "vocalStyle": request.vocal_style,
                "singingVoice": request.singing_voice,
                "vocalIntensity": request.vocal_intensity,
                "genreTags": request.genre_tags,
                "moodTags": request.mood_tags,
                "guidanceScale": request.guidance_scale,
                "allowFallback": request.allow_fallback,
            },
            "parentGenerationId": None,
            "batchId": None,
        }

    def _result_version_details(self, version_details: dict[str, Any], result: GenerationResult) -> dict[str, Any]:
        metadata = result.metadata
        updated = dict(version_details)
        updated["backend"] = metadata.get("backend") or metadata.get("render_backend") or result.generator_name
        updated["modelVersion"] = metadata.get("engine") or metadata.get("model_version")
        updated["generatorName"] = result.generator_name
        updated["outputFile"] = result.file_name
        updated["audio"] = metadata.get("audio")
        return updated
