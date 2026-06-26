from __future__ import annotations

import logging
import subprocess

from app.core.config import Settings
from app.core.errors import ValidationAppError
from app.domain.models import GenerationRequest
from app.generators.registry import GeneratorRegistry
from app.services.job_service import JobService
from app.storage.local_file_store import LocalFileStore
from app.storage.log_store import LogStore
from app.storage.metadata_store import MetadataStore

logger = logging.getLogger(__name__)


class GenerationService:
    def __init__(self, registry: GeneratorRegistry, job_service: JobService, file_store: LocalFileStore, log_store: LogStore, metadata_store: MetadataStore, settings: Settings) -> None:
        self.registry = registry
        self.job_service = job_service
        self.file_store = file_store
        self.log_store = log_store
        self.metadata_store = metadata_store
        self.settings = settings

    def validate_request(self, request: GenerationRequest) -> GenerationRequest:
        generator_name = request.generator or self.settings.default_generator
        if generator_name not in self.registry.names():
            raise ValidationAppError(f"Unknown generator: {generator_name}")
        data = request.model_dump()
        data["generator"] = generator_name
        return GenerationRequest.model_validate(data)

    def run_job(self, job_id: str) -> None:
        job = self.job_service.get_required(job_id)
        log_path = self.log_store.path_for_job(job.id)
        self.log_store.append(job.id, f"job created title={job.request.title!r} generator={job.request.generator}")
        self.job_service.mark_running(job)
        generator_name = job.request.generator or self.settings.default_generator
        try:
            generator = self.registry.get(generator_name)
            output_path = self.file_store.output_path_for_job(job.id)
            self.log_store.append(job.id, f"running generator={generator_name} output={output_path}")
            result = generator.generate(job.request, output_path)
            metadata_path = self.metadata_store.write(job, result)
            self.log_store.append(job.id, f"succeeded file={result.file_name} metadata={metadata_path.name}")
            self.job_service.mark_succeeded(job, result, metadata_file=metadata_path.name, log_file=log_path.name)
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
