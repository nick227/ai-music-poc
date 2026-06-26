from pathlib import Path

from app.core.config import Settings
from app.domain.models import GenerationRequest
from app.generators.ace_step import AceStepCommandGenerator


def test_ace_adapter_falls_back_when_not_configured(tmp_path):
    settings = Settings(DATA_DIR=tmp_path, ACE_ENABLED=False, ACE_COMMAND_TEMPLATE='', ACE_ALLOW_FALLBACK=True)
    generator = AceStepCommandGenerator(settings=settings)
    output = tmp_path / 'out.wav'
    result = generator.generate(GenerationRequest(prompt='dark disco', lyrics='hello', duration_seconds=10, allow_fallback=True), output)
    assert output.exists()
    assert result.generator_name == 'ace-step-command'
    assert result.metadata['backend'] == 'procedural-fallback'


def test_ace_adapter_fails_without_config_or_fallback(tmp_path):
    settings = Settings(DATA_DIR=tmp_path, ACE_ENABLED=False, ACE_COMMAND_TEMPLATE='', ACE_ALLOW_FALLBACK=False)
    generator = AceStepCommandGenerator(settings=settings)
    output = tmp_path / 'out.wav'
    try:
        generator.generate(GenerationRequest(prompt='dark disco', duration_seconds=10, allow_fallback=False), output)
    except RuntimeError as exc:
        assert 'not ready' in str(exc)
    else:
        raise AssertionError('expected RuntimeError')
