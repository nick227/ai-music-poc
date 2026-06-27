from functools import lru_cache

from app.core.config import get_settings
from app.core.paths import ensure_app_dirs
from app.generators.registry import create_default_registry
from app.services.bundle_service import BundleService
from app.services.category_service import CategoryService
from app.services.concept_service import ConceptService
from app.services.generation_service import GenerationService
from app.services.job_service import JobService
from app.services.media_service import MediaService
from app.services.preset_service import PresetService
from app.storage.assignment_store import AssignmentStore
from app.storage.category_store import CategoryStore
from app.storage.concept_store import ConceptStore
from app.storage.local_file_store import LocalFileStore
from app.storage.local_job_store import LocalJobStore
from app.storage.local_media_store import LocalMediaStore
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
def get_media_store():
    settings = get_settings()
    ensure_app_dirs(settings.data_dir)
    return LocalMediaStore(settings.media_dir)


@lru_cache
def get_category_store():
    settings = get_settings()
    ensure_app_dirs(settings.data_dir)
    return CategoryStore(settings.categories_dir)


@lru_cache
def get_concept_store():
    settings = get_settings()
    ensure_app_dirs(settings.data_dir)
    return ConceptStore(settings.concepts_dir)


@lru_cache
def get_assignment_store():
    settings = get_settings()
    ensure_app_dirs(settings.data_dir)
    return AssignmentStore(settings.assignments_dir)


@lru_cache
def get_category_service():
    return CategoryService(get_category_store())


@lru_cache
def get_concept_service():
    return ConceptService(get_concept_store(), get_category_service())


@lru_cache
def get_media_service():
    settings = get_settings()
    return MediaService(
        media_store=get_media_store(),
        assignment_store=get_assignment_store(),
        category_service=get_category_service(),
        concept_service=get_concept_service(),
        settings=settings,
    )


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
        media_store=get_media_store(),
        log_store=get_log_store(),
        metadata_store=get_metadata_store(),
        settings=settings,
    )


@lru_cache
def get_preset_service():
    return PresetService()
