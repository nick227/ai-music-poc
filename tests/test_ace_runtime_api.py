from pathlib import Path

from app.api.routes import ace_runtime
from app.core.config import Settings
from app.core.hardware import AceGenConfig, HardwareProfile


def test_validate_uses_safe_profile_duration_without_recommended_duration(monkeypatch, tmp_path):
    hw = HardwareProfile(
        cuda_available=False,
        checkpoint_dir=str(tmp_path / "checkpoints"),
        safe_recommended_config=AceGenConfig(duration=12),
    )

    monkeypatch.setattr(ace_runtime, "_hardware", lambda settings: hw)
    monkeypatch.setattr(ace_runtime, "check_ace_packages", lambda settings: {"ok": True, "missing_packages": []})

    status = ace_runtime.ace_runtime_validate(
        Settings(
            DATA_DIR=tmp_path,
            ACE_PYTHON=Path("python"),
            ACE_SCRIPT=tmp_path / "runner.py",
            ACE_MODEL_DIR=tmp_path / "checkpoints",
        )
    )

    assert status.last_smoke_test is not None
    assert status.last_smoke_test.duration_seconds == 12
    assert status.last_smoke_test.error == "Skipped: CUDA not available"
