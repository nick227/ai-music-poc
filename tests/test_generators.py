from app.core.config import Settings
from app.generators.registry import create_default_registry


def test_generator_registry_has_defaults(tmp_path):
    registry = create_default_registry(Settings(DATA_DIR=tmp_path))
    assert 'auto-render' in registry.names()
    assert 'procedural-v3' in registry.names()
    assert 'mock-ai' in registry.names()
    assert 'ace-step-command' in registry.names()
