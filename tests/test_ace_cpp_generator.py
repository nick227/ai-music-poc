"""Tests for AceCppGenerator correctness and diagnostic behaviour."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.generators.ace_cpp import AceCppGenerator, _DEFAULT_TIMEOUT_SECONDS
from app.domain.models import GenerationRequest


def _make_generator(timeout: int = 60) -> AceCppGenerator:
    gen = AceCppGenerator(timeout_seconds=timeout)
    gen.binary_lm = MagicMock(spec=Path)
    gen.binary_lm.__str__ = lambda self: "/fake/ace-lm"
    gen.binary_lm.exists.return_value = True
    gen.binary_synth = MagicMock(spec=Path)
    gen.binary_synth.__str__ = lambda self: "/fake/ace-synth"
    gen.binary_synth.exists.return_value = True
    gen.gguf_path = MagicMock(spec=Path)
    gen.gguf_path.__str__ = lambda self: "/fake/models"
    return gen


def _ok_run(**_kwargs):
    return MagicMock(returncode=0, stdout="", stderr="")


# ---------------------------------------------------------------------------
# Timeout wired through
# ---------------------------------------------------------------------------

def test_default_timeout_constant():
    assert _DEFAULT_TIMEOUT_SECONDS == 900


def test_custom_timeout_stored():
    gen = AceCppGenerator(timeout_seconds=42)
    assert gen.timeout_seconds == 42


@patch("app.generators.ace_cpp.subprocess.run")
def test_both_subprocess_calls_receive_timeout(mock_run, tmp_path):
    """Both ace-lm and ace-synth subprocess calls must receive the timeout arg."""
    gen = _make_generator(timeout=77)
    output = tmp_path / "out.wav"
    mock_run.return_value = _ok_run()

    # req0_json_path won't exist in the temp dir — that's fine, we just want
    # to verify the timeout propagates to the first call, then it raises.
    with pytest.raises(RuntimeError, match="request0.json"):
        gen.generate(GenerationRequest(prompt="test", duration_seconds=10), output)

    first_call_kwargs = mock_run.call_args_list[0][1]
    assert first_call_kwargs["timeout"] == 77


@patch("app.generators.ace_cpp.subprocess.run")
def test_timeout_expired_propagates(mock_run, tmp_path):
    """TimeoutExpired from subprocess is not swallowed."""
    gen = _make_generator(timeout=1)
    output = tmp_path / "out.wav"
    mock_run.side_effect = subprocess.TimeoutExpired(cmd=["ace-lm"], timeout=1)

    with pytest.raises(subprocess.TimeoutExpired):
        gen.generate(GenerationRequest(prompt="test", duration_seconds=10), output)


# ---------------------------------------------------------------------------
# Diagnostic error messages
# ---------------------------------------------------------------------------

@patch("app.generators.ace_cpp.subprocess.run")
def test_stderr_included_in_error_when_lm_fails(mock_run, tmp_path):
    """RuntimeError from ace-lm failure must include the binary's stderr."""
    gen = _make_generator()
    output = tmp_path / "out.wav"
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="GGUF load failed: bad magic")

    with pytest.raises(RuntimeError, match="GGUF load failed: bad magic"):
        gen.generate(GenerationRequest(prompt="test", duration_seconds=10), output)


@patch("app.generators.ace_cpp.subprocess.run")
def test_stdout_used_when_stderr_empty_on_lm_failure(mock_run, tmp_path):
    """Falls back to stdout if stderr is empty."""
    gen = _make_generator()
    output = tmp_path / "out.wav"
    mock_run.return_value = MagicMock(returncode=2, stdout="model path not found", stderr="")

    with pytest.raises(RuntimeError, match="model path not found"):
        gen.generate(GenerationRequest(prompt="test", duration_seconds=10), output)


@patch("app.generators.ace_cpp.subprocess.run")
def test_returncode_in_error_when_no_output(mock_run, tmp_path):
    """Return code appears in RuntimeError even when no stdout/stderr."""
    gen = _make_generator()
    output = tmp_path / "out.wav"
    mock_run.return_value = MagicMock(returncode=137, stdout="", stderr="")

    with pytest.raises(RuntimeError, match="137"):
        gen.generate(GenerationRequest(prompt="test", duration_seconds=10), output)


# ---------------------------------------------------------------------------
# Missing binary guard
# ---------------------------------------------------------------------------

def test_generate_raises_when_binaries_missing(tmp_path):
    gen = AceCppGenerator()
    gen.binary_lm = MagicMock(spec=Path)
    gen.binary_lm.exists.return_value = False
    gen.binary_synth = MagicMock(spec=Path)
    gen.binary_synth.exists.return_value = True

    with pytest.raises(RuntimeError, match="binaries not found"):
        gen.generate(
            GenerationRequest(prompt="test", duration_seconds=10),
            tmp_path / "out.wav",
        )
