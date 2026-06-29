"""Tests for DiffSinger backend productization.

Covers: config defaults, command construction, health check TIGER validation,
fallback behaviour, and report_path wiring. Does NOT run real ONNX inference.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from app.generators.svs.command_builder import SvsCommandBuilder
from app.generators.svs.health import get_svs_status


# ── config ──────────────────────────────────────────────────────────────────


def test_mock_backend_is_default():
    settings = Settings()
    assert settings.svs_backend == "mock"
    assert settings.svs_tiger_dir is None
    assert settings.svs_speaker == "tiger_fresh"
    assert settings.svs_diffsinger_python is None


def test_svs_backend_field_accepts_diffsinger(monkeypatch):
    monkeypatch.setenv("SVS_BACKEND", "diffsinger")
    settings = Settings()
    assert settings.svs_backend == "diffsinger"


def test_svs_tiger_dir_parsed_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SVS_TIGER_DIR", str(tmp_path))
    settings = Settings()
    assert settings.svs_tiger_dir == tmp_path


def test_svs_speaker_set_from_env(monkeypatch):
    monkeypatch.setenv("SVS_SPEAKER", "tiger_disco")
    settings = Settings()
    assert settings.svs_speaker == "tiger_disco"


# ── command builder ──────────────────────────────────────────────────────────


def test_mock_backend_command_has_backend_flag(tmp_path):
    settings = Settings()
    builder = SvsCommandBuilder(settings)
    cmd = builder.build(score_path=tmp_path / "score.json", output_path=tmp_path / "out.wav")
    assert "--backend" in cmd
    assert cmd[cmd.index("--backend") + 1] == "mock"


def test_report_path_appended_to_mock_command(tmp_path):
    settings = Settings()
    builder = SvsCommandBuilder(settings)
    report = tmp_path / "report.json"
    cmd = builder.build(
        score_path=tmp_path / "score.json",
        output_path=tmp_path / "out.wav",
        report_path=report,
    )
    assert "--report" in cmd
    assert cmd[cmd.index("--report") + 1] == str(report)


def test_diffsinger_command_includes_tiger_dir_and_speaker(tmp_path, monkeypatch):
    tiger = tmp_path / "tiger"
    monkeypatch.setenv("SVS_BACKEND", "diffsinger")
    monkeypatch.setenv("SVS_TIGER_DIR", str(tiger))
    monkeypatch.setenv("SVS_SPEAKER", "tiger_vinyl")

    settings = Settings()
    builder = SvsCommandBuilder(settings)
    cmd = builder.build(score_path=tmp_path / "score.json", output_path=tmp_path / "out.wav")

    assert "--backend" in cmd
    assert cmd[cmd.index("--backend") + 1] == "diffsinger"
    assert "--tiger-dir" in cmd
    assert cmd[cmd.index("--tiger-dir") + 1] == str(tiger)
    assert "--speaker" in cmd
    assert cmd[cmd.index("--speaker") + 1] == "tiger_vinyl"


def test_diffsinger_command_includes_report_path(tmp_path, monkeypatch):
    monkeypatch.setenv("SVS_BACKEND", "diffsinger")
    monkeypatch.setenv("SVS_TIGER_DIR", str(tmp_path / "tiger"))

    settings = Settings()
    builder = SvsCommandBuilder(settings)
    report = tmp_path / "svs_report.json"
    cmd = builder.build(
        score_path=tmp_path / "score.json",
        output_path=tmp_path / "out.wav",
        report_path=report,
    )
    assert "--report" in cmd
    assert cmd[cmd.index("--report") + 1] == str(report)


def test_diffsinger_python_override_included(tmp_path, monkeypatch):
    fake_python = tmp_path / "venv/bin/python"
    monkeypatch.setenv("SVS_BACKEND", "diffsinger")
    monkeypatch.setenv("SVS_TIGER_DIR", str(tmp_path / "tiger"))
    monkeypatch.setenv("SVS_DIFFSINGER_PYTHON", str(fake_python))

    settings = Settings()
    builder = SvsCommandBuilder(settings)
    cmd = builder.build(score_path=tmp_path / "score.json", output_path=tmp_path / "out.wav")

    assert "--diffsinger-python" in cmd
    assert cmd[cmd.index("--diffsinger-python") + 1] == str(fake_python)


def test_custom_template_not_overridden_by_backend(tmp_path, monkeypatch):
    template = "echo $score_path $output_path"
    monkeypatch.setenv("SVS_COMMAND_TEMPLATE", template)
    monkeypatch.setenv("SVS_BACKEND", "diffsinger")

    settings = Settings()
    builder = SvsCommandBuilder(settings)
    cmd = builder.build(score_path=tmp_path / "score.json", output_path=tmp_path / "out.wav")
    # Custom template is used as-is (no --tiger-dir injected)
    assert "--tiger-dir" not in cmd


# ── health check ─────────────────────────────────────────────────────────────


def test_health_warns_when_diffsinger_tiger_dir_unset(monkeypatch):
    monkeypatch.setenv("SVS_BACKEND", "diffsinger")
    monkeypatch.setenv("SVS_ENABLED", "true")
    monkeypatch.delenv("SVS_TIGER_DIR", raising=False)

    settings = Settings()
    status = get_svs_status(settings)
    assert any("SVS_TIGER_DIR" in w for w in status["warnings"])
    assert status["can_generate"] is False


def test_health_warns_when_tiger_dir_missing(tmp_path, monkeypatch):
    missing = tmp_path / "nonexistent_tiger"
    monkeypatch.setenv("SVS_BACKEND", "diffsinger")
    monkeypatch.setenv("SVS_ENABLED", "true")
    monkeypatch.setenv("SVS_TIGER_DIR", str(missing))

    settings = Settings()
    status = get_svs_status(settings)
    assert any("does not exist" in w or "SVS_TIGER_DIR" in w for w in status["warnings"])
    assert status["can_generate"] is False


def test_health_warns_when_acoustic_onnx_missing(tmp_path, monkeypatch):
    tiger = tmp_path / "tiger"
    (tiger / "dsacoustic").mkdir(parents=True)
    # No acoustic.onnx created
    monkeypatch.setenv("SVS_BACKEND", "diffsinger")
    monkeypatch.setenv("SVS_ENABLED", "true")
    monkeypatch.setenv("SVS_TIGER_DIR", str(tiger))

    settings = Settings()
    status = get_svs_status(settings)
    assert any("acoustic.onnx" in w for w in status["warnings"])
    assert status["can_generate"] is False


def test_health_ready_when_tiger_dir_complete(tmp_path, monkeypatch):
    tiger = tmp_path / "tiger"
    acoustic_dir = tiger / "dsacoustic"
    acoustic_dir.mkdir(parents=True)
    (acoustic_dir / "acoustic.onnx").touch()

    monkeypatch.setenv("SVS_BACKEND", "diffsinger")
    monkeypatch.setenv("SVS_ENABLED", "true")
    monkeypatch.setenv("SVS_TIGER_DIR", str(tiger))
    # Use current Python to avoid SVS_PYTHON check warnings
    import sys
    monkeypatch.setenv("SVS_PYTHON", sys.executable)

    settings = Settings()
    status = get_svs_status(settings)
    tiger_warnings = [w for w in status["warnings"] if "TIGER" in w or "acoustic" in w or "tiger" in w.lower()]
    assert not tiger_warnings, f"Unexpected TIGER warnings: {tiger_warnings}"
    assert status["can_generate"] is True


def test_health_status_includes_svs_backend_field(monkeypatch):
    monkeypatch.setenv("SVS_BACKEND", "diffsinger")
    settings = Settings()
    status = get_svs_status(settings)
    assert "svs_backend" in status
    assert status["svs_backend"] == "diffsinger"


def test_health_mock_backend_has_no_tiger_warnings():
    settings = Settings()
    assert settings.svs_backend == "mock"
    status = get_svs_status(settings)
    tiger_warnings = [w for w in status["warnings"] if "TIGER" in w or "tiger" in w.lower()]
    assert not tiger_warnings, f"mock backend should not warn about TIGER: {tiger_warnings}"


# ── fallback control ─────────────────────────────────────────────────────────


def test_fallback_disabled_raises_when_tiger_dir_missing(tmp_path, monkeypatch):
    from app.domain.models import GenerationRequest
    from app.generators.procedural import ProceduralGenerator
    from app.generators.svs.adapter import SvsCommandGenerator

    monkeypatch.setenv("SVS_BACKEND", "diffsinger")
    monkeypatch.setenv("SVS_TIGER_DIR", str(tmp_path / "nonexistent"))
    monkeypatch.setenv("SVS_ALLOW_FALLBACK", "false")
    monkeypatch.setenv("SVS_ENABLED", "true")

    settings = Settings()
    generator = SvsCommandGenerator(settings=settings, fallback=ProceduralGenerator())

    request = GenerationRequest.model_validate({
        "title": "Fallback test",
        "prompt": "pop vocal",
        "lyrics": "Verse:\nhello world\n",
        "duration_seconds": 10,
        "mode": "vocal_demo",
    })

    with pytest.raises((RuntimeError, Exception)):
        generator.generate(request, tmp_path / "out.wav")
