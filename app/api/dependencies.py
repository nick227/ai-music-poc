from functools import lru_cache

from app.core.config import get_settings
from app.core.paths import ensure_app_dirs
from app.generators.registry import create_default_registry
from app.services.bundle_service import BundleService
from app.services.generation_service import GenerationService
from app.services.job_service import JobService
from app.services.preset_service import PresetService
from app.storage.local_file_store import LocalFileStore
from app.storage.local_job_store import LocalJobStore
from app.storage.log_store import LogStore
from app.storage.metadata_store import MetadataStore


@lru_cache
def get_registry():
    settings = get_settings()
    ensure_app_dirs(settings.data_dir)
    return create_default_registry(settings)


@lru_cache
def get_job_service():
    settings = get_settings()
    ensure_app_dirs(settings.data_dir)
    return JobService(LocalJobStore(settings.job_dir))


@lru_cache
def get_file_store():
    settings = get_settings()
    ensure_app_dirs(settings.data_dir)
    return LocalFileStore(settings.output_dir)


@lru_cache
def get_log_store():
    settings = get_settings()
    ensure_app_dirs(settings.data_dir)
    return LogStore(settings.log_dir)


@lru_cache
def get_metadata_store():
    settings = get_settings()
    ensure_app_dirs(settings.data_dir)
    return MetadataStore(settings.output_dir, settings)


@lru_cache
def get_bundle_service():
    return BundleService(get_file_store(), get_metadata_store(), get_log_store())


@lru_cache
def get_generation_service():
    settings = get_settings()
    return GenerationService(
        registry=get_registry(),
        job_service=get_job_service(),
        file_store=get_file_store(),
        log_store=get_log_store(),
        metadata_store=get_metadata_store(),
        settings=settings,
    )


@lru_cache
def get_preset_service():
    return PresetService()
