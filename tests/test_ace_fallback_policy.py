"""
ACE fallback policy tests.
Verifies that fallback is only allowed when BOTH the settings flag (ACE_ALLOW_FALLBACK)
AND the per-request flag (request.allow_fallback) are True.
"""
from pathlib import Path

import pytest

from app.core.config import Settings
from app.domain.models import GenerationRequest
from app.generators.ace_step import AceStepCommandGenerator


def _req(**overrides) -> GenerationRequest:
    data = {
        "prompt": "dark electro test",
        "lyrics": "verse",
        "duration_seconds": 10,
        "allow_fallback": True,
    }
    data.update(overrides)
    return GenerationRequest.model_validate(data)


def _generator(tmp_path: Path, allow_fallback: bool) -> AceStepCommandGenerator:
    return AceStepCommandGenerator(
        settings=Settings(
            DATA_DIR=tmp_path,
            ACE_ENABLED=False,
            ACE_COMMAND_TEMPLATE="",
            ACE_ALLOW_FALLBACK=allow_fallback,
        )
    )


# ---------------------------------------------------------------------------
# Baseline: both flags True → fallback succeeds
# ---------------------------------------------------------------------------

def test_fallback_succeeds_when_both_flags_true(tmp_path):
    gen = _generator(tmp_path, allow_fallback=True)
    output = tmp_path / "out.wav"
    result = gen.generate(_req(allow_fallback=True), output)
    assert output.exists()
    assert result.metadata["backend"] == "procedural-fallback"


# ---------------------------------------------------------------------------
# Settings flag False → fallback blocked regardless of request flag
# ---------------------------------------------------------------------------

def test_fallback_blocked_when_settings_flag_false(tmp_path):
    gen = _generator(tmp_path, allow_fallback=False)
    output = tmp_path / "out.wav"
    with pytest.raises(RuntimeError, match="not ready"):
        gen.generate(_req(allow_fallback=True), output)


# ---------------------------------------------------------------------------
# Request flag False → fallback blocked regardless of settings flag
# ---------------------------------------------------------------------------

def test_fallback_blocked_when_request_flag_false(tmp_path):
    gen = _generator(tmp_path, allow_fallback=True)
    output = tmp_path / "out.wav"
    with pytest.raises(RuntimeError, match="not ready"):
        gen.generate(_req(allow_fallback=False), output)


# ---------------------------------------------------------------------------
# Both flags False → fallback blocked
# ---------------------------------------------------------------------------

def test_fallback_blocked_when_both_flags_false(tmp_path):
    gen = _generator(tmp_path, allow_fallback=False)
    output = tmp_path / "out.wav"
    with pytest.raises(RuntimeError, match="not ready"):
        gen.generate(_req(allow_fallback=False), output)


# ---------------------------------------------------------------------------
# Fallback result metadata
# ---------------------------------------------------------------------------

def test_fallback_result_carries_reason_and_backend(tmp_path):
    gen = _generator(tmp_path, allow_fallback=True)
    output = tmp_path / "out.wav"
    result = gen.generate(_req(allow_fallback=True), output)
    assert result.metadata["backend"] == "procedural-fallback"
    assert "fallback_reason" in result.metadata
    assert result.generator_name == "ace-step-command"


def test_fallback_result_is_valid_wav(tmp_path):
    gen = _generator(tmp_path, allow_fallback=True)
    output = tmp_path / "fallback.wav"
    gen.generate(_req(allow_fallback=True), output)
    assert output.exists()
    assert output.stat().st_size > 1000  # non-trivial WAV
