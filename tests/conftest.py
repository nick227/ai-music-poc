import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import get_settings
from app.main import create_app


def clear_caches():
    get_settings.cache_clear()
    dependencies.get_job_service.cache_clear()
    dependencies.get_file_store.cache_clear()
    dependencies.get_media_store.cache_clear()
    dependencies.get_category_store.cache_clear()
    dependencies.get_concept_store.cache_clear()
    dependencies.get_assignment_store.cache_clear()
    dependencies.get_category_service.cache_clear()
    dependencies.get_concept_service.cache_clear()
    dependencies.get_media_service.cache_clear()
    dependencies.get_log_store.cache_clear()
    dependencies.get_metadata_store.cache_clear()
    dependencies.get_bundle_service.cache_clear()
    dependencies.get_generation_service.cache_clear()
    dependencies.get_song_service.cache_clear()
    dependencies.get_registry.cache_clear()
    dependencies.get_preset_service.cache_clear()


@pytest.fixture()
def client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("DATA_DIR", tmp)
        monkeypatch.setenv("DEFAULT_GENERATOR", "procedural-v3")
        monkeypatch.setenv("ACE_ENABLED", "false")
        monkeypatch.setenv("ACE_COMMAND_TEMPLATE", "")
        clear_caches()
        app = create_app()
        with TestClient(app) as c:
            yield c, Path(tmp)
        clear_caches()
