from pathlib import Path

from app.core.config import Settings
from app.domain.models import GenerationRequest
from app.generators.ace_step import AceStepCommandGenerator
from app.generators.auto_render import AutoRenderGenerator
from app.generators.procedural import ProceduralGenerator


def _generator(settings: Settings) -> AutoRenderGenerator:
    procedural = ProceduralGenerator()
    ace = AceStepCommandGenerator(settings=settings, fallback=procedural)
    return AutoRenderGenerator(procedural=procedural, ace=ace)


def test_auto_render_routes_draft_to_parametric(tmp_path: Path):
    generator = _generator(Settings(DATA_DIR=tmp_path, ACE_ENABLED=False, ACE_COMMAND_TEMPLATE="", ACE_ALLOW_FALLBACK=True))
    result = generator.generate(
        GenerationRequest(prompt="dark cinematic piano", lyrics="hello night", duration_seconds=10, quality="draft"),
        tmp_path / "draft.wav",
    )
    assert result.generator_name == "auto-render"
    assert result.metadata["render_route"] == "draft-parametric"
    assert result.metadata["render_backend"] == "procedural-v3"


def test_auto_render_routes_balanced_to_ace_with_fallback(tmp_path: Path):
    generator = _generator(Settings(DATA_DIR=tmp_path, ACE_ENABLED=False, ACE_COMMAND_TEMPLATE="", ACE_ALLOW_FALLBACK=True))
    result = generator.generate(
        GenerationRequest(
            prompt="french disco",
            lyrics="hello night",
            duration_seconds=10,
            quality="balanced",
            allow_fallback=True,
        ),
        tmp_path / "final.wav",
    )
    assert result.generator_name == "auto-render"
    assert result.metadata["render_route"] == "final-neural"
    assert result.metadata["render_backend"] == "ace-step-command"
    assert result.metadata["backend"] == "procedural-fallback"
