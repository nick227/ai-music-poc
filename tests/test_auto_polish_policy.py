from app.domain.models import GenerationResult
from app.services.generation_service import should_auto_polish


def test_skip_auto_polish_for_procedural_draft():
    result = GenerationResult(
        file_name="x.wav",
        duration_seconds=10,
        sample_rate=44100,
        generator_name="procedural-v3",
        metadata={"engine": "procedural-v3.32", "render_route": "draft-parametric"},
    )
    assert should_auto_polish(result) is False


def test_auto_polish_for_ace_render():
    result = GenerationResult(
        file_name="x.wav",
        duration_seconds=10,
        sample_rate=44100,
        generator_name="ace-step-command",
        metadata={"render_route": "final-neural", "render_backend": "ace-step-command"},
    )
    assert should_auto_polish(result) is True
