"""Tests for compare_ace_python_vs_cpp.run_cpp_ace correctness."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# Import the function under test without executing __main__
from scripts.compare_ace_python_vs_cpp import run_cpp_ace

REPO = "/home/administrator/models/acestep.cpp"
BINARY_LM = f"{REPO}/build/ace-lm"
BINARY_SYNTH = f"{REPO}/build/ace-synth"


def _both_binaries_exist(p: str) -> bool:
    return p in (BINARY_LM, BINARY_SYNTH)


# ---------------------------------------------------------------------------
# Returns False (not True) when ace-synth produces no output file
# ---------------------------------------------------------------------------

@patch("scripts.compare_ace_python_vs_cpp.subprocess.run")
@patch("scripts.compare_ace_python_vs_cpp.os.path.exists")
def test_returns_false_when_generated_audio_missing(mock_exists, mock_run, tmp_path):
    """Never report success when the final audio file was not produced."""
    output = tmp_path / "out.wav"
    mock_run.return_value = MagicMock(returncode=0)

    # Binaries exist; synth_request_file exists; generated_audio does NOT exist.
    def exists_side_effect(p):
        if p in (BINARY_LM, BINARY_SYNTH):
            return True
        if "request0.json" in str(p):
            return True  # synth_request_file is present
        if "request00" in str(p):
            return False  # final audio missing
        return False

    mock_exists.side_effect = exists_side_effect

    elapsed, success = run_cpp_ace("test prompt", 42, 10, output)
    assert success is False


@patch("scripts.compare_ace_python_vs_cpp.subprocess.run")
@patch("scripts.compare_ace_python_vs_cpp.os.path.exists")
def test_returns_false_when_synth_request_missing(mock_exists, mock_run, tmp_path):
    """Return False immediately if ace-lm did not produce request0.json."""
    output = tmp_path / "out.wav"
    mock_run.return_value = MagicMock(returncode=0)

    def exists_side_effect(p):
        if p in (BINARY_LM, BINARY_SYNTH):
            return True
        return False  # request0.json absent

    mock_exists.side_effect = exists_side_effect

    elapsed, success = run_cpp_ace("test prompt", 42, 10, output)
    assert success is False
    # ace-synth must NOT have been launched
    for c in mock_run.call_args_list:
        cmd = c[0][0]
        assert "ace-synth" not in " ".join(cmd), "ace-synth should not be called when request0.json is missing"


@patch("scripts.compare_ace_python_vs_cpp.subprocess.run")
@patch("scripts.compare_ace_python_vs_cpp.os.path.exists")
def test_returns_false_when_binaries_missing(mock_exists, mock_run, tmp_path):
    output = tmp_path / "out.wav"
    mock_exists.return_value = False

    elapsed, success = run_cpp_ace("test prompt", 42, 10, output)
    assert success is False
    assert elapsed == 0
    mock_run.assert_not_called()


@patch("scripts.compare_ace_python_vs_cpp.subprocess.run")
@patch("scripts.compare_ace_python_vs_cpp.os.path.exists")
def test_returns_false_on_called_process_error(mock_exists, mock_run, tmp_path):
    output = tmp_path / "out.wav"
    mock_exists.side_effect = _both_binaries_exist
    mock_run.side_effect = subprocess.CalledProcessError(1, ["ace-lm"])

    elapsed, success = run_cpp_ace("test prompt", 42, 10, output)
    assert success is False
    assert elapsed == 0


# ---------------------------------------------------------------------------
# Isolation: temp directory used (no hardcoded /tmp paths)
# ---------------------------------------------------------------------------

@patch("scripts.compare_ace_python_vs_cpp.shutil.copy")
@patch("scripts.compare_ace_python_vs_cpp.subprocess.run")
@patch("scripts.compare_ace_python_vs_cpp.os.path.exists")
def test_uses_temp_dir_not_slash_tmp(mock_exists, mock_run, mock_copy, tmp_path):
    """Request files must not be placed at hardcoded /tmp paths."""
    output = tmp_path / "out.wav"
    mock_run.return_value = MagicMock(returncode=0)
    captured_paths: list[str] = []

    def exists_side_effect(p):
        captured_paths.append(str(p))
        if p in (BINARY_LM, BINARY_SYNTH):
            return True
        if "request0.json" in str(p):
            return True
        if "request00" in str(p):
            return True
        return False

    mock_exists.side_effect = exists_side_effect

    run_cpp_ace("test prompt", 42, 10, output)

    # No path passed to os.path.exists should be under the literal /tmp root
    # with the old hardcoded filenames.
    for p in captured_paths:
        assert p not in (
            "/tmp/compare_request.json",
            "/tmp/compare_request0.json",
            "/tmp/compare_request00.wav",
            "/tmp/compare_request00.mp3",
        ), f"Hardcoded /tmp path detected: {p}"
