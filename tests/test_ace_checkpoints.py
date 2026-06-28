from pathlib import Path

from app.core.ace_profiles import XL_SFT_CHECKPOINT, xl_sft_installed
from app.generators.ace_step.checkpoints import resolve_generation_plan


def test_balanced_uses_turbo_when_xl_disabled(tmp_path: Path) -> None:
    (tmp_path / "acestep-v15-turbo").mkdir()
    xl = tmp_path / XL_SFT_CHECKPOINT
    xl.mkdir()
    (xl / "model.safetensors.index.json").write_text('{"weight_map":{"w":"model-00001-of-00002.safetensors"}}', encoding="utf-8")
    (xl / "model-00001-of-00002.safetensors").write_bytes(b"x" * 16)
    (xl / "model-00002-of-00002.safetensors").write_bytes(b"x" * 16)
    checkpoint, steps, is_turbo = resolve_generation_plan(quality="balanced", checkpoint_dir=tmp_path)
    assert checkpoint == "acestep-v15-turbo"
    assert steps == 8
    assert is_turbo is True


def test_high_uses_turbo_clamped(tmp_path: Path) -> None:
    (tmp_path / "acestep-v15-turbo").mkdir()
    checkpoint, steps, is_turbo = resolve_generation_plan(quality="high", checkpoint_dir=tmp_path)
    assert checkpoint == "acestep-v15-turbo"
    assert steps == 8
    assert is_turbo is True


def test_turbo_only_clamps_steps(tmp_path: Path) -> None:
    (tmp_path / "acestep-v15-turbo").mkdir()
    checkpoint, steps, is_turbo = resolve_generation_plan(quality="balanced", checkpoint_dir=tmp_path)
    assert checkpoint == "acestep-v15-turbo"
    assert steps == 8
    assert is_turbo is True


def test_xl_routing_when_app_enabled(monkeypatch, tmp_path: Path) -> None:
    import app.generators.ace_step.checkpoints as ckpt_mod

    monkeypatch.setattr(ckpt_mod, "XL_SFT_APP_ENABLED", True)
    (tmp_path / "acestep-v15-turbo").mkdir()
    xl = tmp_path / XL_SFT_CHECKPOINT
    xl.mkdir()
    (xl / "model.safetensors").write_bytes(b"x" * 16)
    assert xl_sft_installed(tmp_path)
    checkpoint, steps, is_turbo = resolve_generation_plan(quality="high", checkpoint_dir=tmp_path)
    assert checkpoint == XL_SFT_CHECKPOINT
    assert steps == 50
    assert is_turbo is False
