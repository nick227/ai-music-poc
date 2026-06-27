from functools import lru_cache

from app.core.config import get_settings
from app.core.paths import ensure_app_dirs
from app.generators.registry import create_default_registry
from app.services.bundle_service import BundleService
from app.services.category_service import CategoryService
from app.services.concept_service import ConceptService
from app.services.generation_service import GenerationService
from app.services.ingestion_service import IngestionService
from app.services.style_version_service import StyleVersionService
from app.services.job_service import JobService
from app.services.media_service import MediaService
from app.services.preset_service import PresetService
from app.services.song_service import SongService
from app.storage.assignment_store import AssignmentStore
from app.storage.category_store import CategoryStore
from app.storage.concept_store import ConceptStore
from app.storage.local_file_store import LocalFileStore
from app.storage.local_job_store import LocalJobStore
from app.storage.local_media_store import LocalMediaStore
from app.storage.log_store import LogStore
from app.storage.metadata_store import MetadataStore
from app.storage.style_version_store import StyleVersionStore
from app.services.training_service import TrainingService
from app.storage.training_run_store import TrainingRunStore
from app.training.mock_adapter import MockTrainingAdapter
from app.services.slice_package_service import SlicePackageService
from app.services.slice_service import SliceService
from app.storage.slice_store import SliceStore


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
        style_version_service=get_style_version_service(),
        settings=settings,
    )


@lru_cache
def get_slice_store():
    settings = get_settings()
    ensure_app_dirs(settings.data_dir)
    return SliceStore(settings.slices_dir)


@lru_cache
def get_slice_package_service():
    settings = get_settings()
    return SlicePackageService(
        get_slice_store(),
        get_media_store(),
        get_assignment_store(),
        get_category_service(),
        settings,
    )


@lru_cache
def get_slice_service():
    return SliceService(
        get_slice_store(),
        get_media_store(),
        get_assignment_store(),
        get_category_service(),
        get_concept_service(),
        get_slice_package_service(),
    )


@lru_cache
def get_training_run_store():
    settings = get_settings()
    ensure_app_dirs(settings.data_dir)
    return TrainingRunStore(settings.training_runs_dir)


@lru_cache
def get_mock_training_adapter():
    settings = get_settings()
    return MockTrainingAdapter(get_training_run_store(), step_delay_seconds=settings.training_mock_step_delay_seconds)


@lru_cache
def get_style_version_store():
    settings = get_settings()
    ensure_app_dirs(settings.data_dir)
    return StyleVersionStore(settings.style_versions_dir)


@lru_cache
def get_style_version_service():
    return StyleVersionService(get_style_version_store())


@lru_cache
def get_ingestion_service():
    return IngestionService(get_media_store(), get_assignment_store())


@lru_cache
def get_training_service():
    settings = get_settings()
    return TrainingService(
        get_training_run_store(),
        get_slice_service(),
        get_mock_training_adapter(),
        get_ingestion_service(),
        get_style_version_service(),
        settings,
    )


@lru_cache
def get_song_service():
    return SongService(get_media_store(), get_job_service())


@lru_cache
def get_preset_service():
    return PresetService()
