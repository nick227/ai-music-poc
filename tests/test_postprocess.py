import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.audio.postprocess import auto_polish


def test_auto_polish_skip_on_missing(tmp_path: Path):
    target = tmp_path / "missing.wav"
    metadata = auto_polish(target, "ace-cpp", "balanced")
    assert metadata["postprocess_skipped"] is True
    assert metadata["postprocess_skip_reason"] == "file_not_found"


def test_auto_polish_ffmpeg_fallback(tmp_path: Path, monkeypatch):
    # Mock pedalboard import to raise ImportError
    import builtins
    real_import = builtins.__import__

    def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'pedalboard':
            raise ImportError("Mocked missing pedalboard")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, '__import__', mock_import)

    # Create dummy wav
    target = tmp_path / "test.wav"
    target.write_bytes(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")

    # Mock ffmpeg to succeed
    def mock_run(cmd, *args, **kwargs):
        if "ffmpeg" in cmd:
            if "-version" in cmd:
                return subprocess.CompletedProcess(cmd, 0, b"ffmpeg version 6.0")
            # simulate ffmpeg writing a new file
            target.write_bytes(b"polished audio")
            return subprocess.CompletedProcess(cmd, 0, b"")
        raise FileNotFoundError()
        
    monkeypatch.setattr(subprocess, "run", mock_run)

    metadata = auto_polish(target, "ace-cpp", "balanced")
    
    assert metadata["postprocess_enabled"] is True
    assert metadata["chain_used"] == "ffmpeg"
    assert "Pedalboard not installed" in "".join(metadata["warnings"])
    assert target.exists()
    assert target.read_bytes() == b"polished audio"
    
    raw_path = tmp_path / "test_raw.wav"
    assert raw_path.exists()
    assert raw_path.read_bytes().startswith(b"RIFF")
    
    json_path = tmp_path / "test_postprocess.json"
    assert json_path.exists()


def test_auto_polish_all_fail_graceful_restore(tmp_path: Path, monkeypatch):
    # Create dummy wav
    target = tmp_path / "test.wav"
    target.write_bytes(b"original")

    # Force pedalboard import to fail
    import builtins
    real_import = builtins.__import__
    def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'pedalboard':
            raise ImportError()
        return real_import(name, globals, locals, fromlist, level)
    monkeypatch.setattr(builtins, '__import__', mock_import)

    # Force ffmpeg to fail
    def mock_run(*args, **kwargs):
        raise FileNotFoundError("ffmpeg not found")
    monkeypatch.setattr(subprocess, "run", mock_run)

    metadata = auto_polish(target, "ace-cpp", "balanced")
    
    assert metadata["postprocess_skipped"] is True
    assert metadata["chain_used"] == "none"
    assert not target.exists()
    assert (tmp_path / "test_raw.wav").exists()
    assert (tmp_path / "test_raw.wav").read_bytes() == b"original"


def test_auto_polish_skipped_for_procedural(tmp_path: Path):
    target = tmp_path / "test.wav"
    target.write_bytes(b"original")

    metadata = auto_polish(target, "procedural", "balanced")

    assert metadata["postprocess_enabled"] is False
    assert metadata["postprocess_skipped"] is True
    assert target.exists()
    assert target.read_bytes() == b"original"
    assert (tmp_path / "test_raw.wav").exists()
