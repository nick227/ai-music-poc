from pathlib import Path

from app.core.ace_profiles import (
    FINAL_SFT_CHECKPOINT,
    FINAL_SFT_LM,
    FINAL_SFT_NAME,
    build_final_render_profiles,
    build_final_sft_profile,
    final_sft_installed,
)
from app.core.ace_runtime import build_runtime_status
from app.core.hardware import build_hardware_profile
from scripts.compare_ace_turbo_vs_sft import build_variants


def test_final_sft_profile_shape() -> None:
    profile = build_final_sft_profile(inference_steps=24)
    assert profile.name == FINAL_SFT_NAME
    assert profile.checkpoint == FINAL_SFT_CHECKPOINT
    assert profile.inference_steps == 24
    assert profile.batch_size == 1
    assert profile.offload_to_cpu is True
    assert profile.lm_model == FINAL_SFT_LM


def test_final_sft_installed_requires_weights(tmp_path: Path) -> None:
    assert final_sft_installed(tmp_path) is False
    ckpt_dir = tmp_path / FINAL_SFT_CHECKPOINT
    ckpt_dir.mkdir()
    assert final_sft_installed(tmp_path) is False
    (ckpt_dir / "model.safetensors").write_bytes(b"x" * 16)
    assert final_sft_installed(tmp_path) is True


def test_build_final_render_profiles_when_missing(tmp_path: Path) -> None:
    assert build_final_render_profiles(tmp_path) == []


def test_build_final_render_profiles_when_present(tmp_path: Path) -> None:
    ckpt_dir = tmp_path / FINAL_SFT_CHECKPOINT
    ckpt_dir.mkdir()
    (ckpt_dir / "model.safetensors").write_bytes(b"x" * 16)
    profiles = build_final_render_profiles(tmp_path)
    assert len(profiles) == 2
    assert {p.inference_steps for p in profiles} == {24, 50}


def test_hardware_profile_includes_final_render_profiles(tmp_path: Path) -> None:
    turbo = tmp_path / "acestep-v15-turbo"
    turbo.mkdir()
    sft = tmp_path / FINAL_SFT_CHECKPOINT
    sft.mkdir()
    (sft / "model.safetensors").write_bytes(b"x" * 16)
    (tmp_path / "vae").mkdir()

    hw = build_hardware_profile(checkpoint_dir=tmp_path)
    assert hw.final_sft_available is True
    assert len(hw.final_render_profiles) == 2
    assert hw.safe_recommended_config is not None
    assert hw.safe_recommended_config.checkpoint == "acestep-v15-turbo"


def test_missing_final_sft_does_not_block_checkpoints_ok(tmp_path: Path) -> None:
    turbo = tmp_path / "acestep-v15-turbo"
    turbo.mkdir()
    (tmp_path / "vae").mkdir()
    hw = build_hardware_profile(checkpoint_dir=tmp_path)
    status = build_runtime_status(hw, packages_ok=True, last_smoke_test=None)
    assert status.final_render_warning
    assert "optional final-render checkpoint missing" in status.final_render_warning
    assert status.checkpoints_ok is True


def test_compare_variants_skip_sft_when_missing() -> None:
    variants = build_variants(include_sft=False)
    assert len(variants) == 1
    assert variants[0]["id"] == "turbo_8"


def test_compare_variants_include_sft_when_present() -> None:
    variants = build_variants(include_sft=True)
    assert [v["id"] for v in variants] == ["turbo_8", "sft_24", "sft_50"]
