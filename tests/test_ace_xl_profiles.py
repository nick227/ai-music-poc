from pathlib import Path

from app.core.ace_profiles import (
    FINAL_XL_SFT_24,
    FINAL_XL_SFT_50,
    PROFILE_LM,
    XL_SFT_CHECKPOINT,
    XL_TURBO_8,
    XL_TURBO_CHECKPOINT,
    build_final_render_profiles,
    build_xl_sft_profile,
    build_xl_turbo_profile,
    xl_sft_installed,
    xl_turbo_installed,
)
from app.core.ace_runtime import build_runtime_status
from app.core.hardware import build_hardware_profile
from scripts.compare_ace_xl import build_variants


def test_xl_sft_profile_shape() -> None:
    profile = build_xl_sft_profile(inference_steps=24)
    assert profile.name == FINAL_XL_SFT_24
    assert profile.checkpoint == XL_SFT_CHECKPOINT
    assert profile.inference_steps == 24
    assert profile.lm_model == PROFILE_LM


def test_xl_turbo_profile_shape() -> None:
    profile = build_xl_turbo_profile()
    assert profile.name == XL_TURBO_8
    assert profile.checkpoint == XL_TURBO_CHECKPOINT
    assert profile.inference_steps == 8


def test_xl_sft_installed_accepts_sharded_layout(tmp_path: Path) -> None:
    ckpt_dir = tmp_path / XL_SFT_CHECKPOINT
    import json

    ckpt_dir.mkdir()
    shards = [f"model-{i:05d}-of-00004.safetensors" for i in range(1, 5)]
    weight_map = {f"w{i}": shards[i % 4] for i in range(4)}
    (ckpt_dir / "model.safetensors.index.json").write_text(json.dumps({"weight_map": weight_map}), encoding="utf-8")
    for name in shards:
        (ckpt_dir / name).write_bytes(b"x" * 16)
    assert xl_sft_installed(tmp_path) is True


def test_build_final_render_profiles_xl_only(tmp_path: Path) -> None:
    ckpt_dir = tmp_path / XL_SFT_CHECKPOINT
    ckpt_dir.mkdir()
    (ckpt_dir / "model.safetensors").write_bytes(b"x" * 16)
    profiles = build_final_render_profiles(tmp_path)
    assert len(profiles) == 2
    assert {p.name for p in profiles} == {FINAL_XL_SFT_24, FINAL_XL_SFT_50}


def test_hardware_profile_keeps_turbo_safe(tmp_path: Path) -> None:
    turbo = tmp_path / "acestep-v15-turbo"
    turbo.mkdir()
    xl = tmp_path / XL_SFT_CHECKPOINT
    xl.mkdir()
    (xl / "model.safetensors").write_bytes(b"x" * 16)
    (tmp_path / "vae").mkdir()

    hw = build_hardware_profile(checkpoint_dir=tmp_path)
    assert hw.xl_sft_available is True
    assert len(hw.final_render_profiles) == 2
    assert hw.safe_recommended_config is not None
    assert hw.safe_recommended_config.checkpoint == "acestep-v15-turbo"


def test_missing_xl_does_not_block_checkpoints_ok(tmp_path: Path) -> None:
    turbo = tmp_path / "acestep-v15-turbo"
    turbo.mkdir()
    (tmp_path / "vae").mkdir()
    hw = build_hardware_profile(checkpoint_dir=tmp_path)
    status = build_runtime_status(hw, packages_ok=True, last_smoke_test=None)
    assert status.final_render_warning
    assert XL_SFT_CHECKPOINT in status.final_render_warning
    assert status.checkpoints_ok is True


def test_installed_xl_disabled_warning(tmp_path: Path) -> None:
    turbo = tmp_path / "acestep-v15-turbo"
    turbo.mkdir()
    xl = tmp_path / XL_SFT_CHECKPOINT
    xl.mkdir()
    (xl / "model.safetensors").write_bytes(b"x" * 16)
    (tmp_path / "vae").mkdir()
    hw = build_hardware_profile(checkpoint_dir=tmp_path)
    status = build_runtime_status(hw, packages_ok=True, last_smoke_test=None)
    assert "disabled for app generation" in status.final_render_warning


def test_compare_variants_skip_xl_when_missing() -> None:
    variants, skipped = build_variants(xl_sft_ready=False, xl_turbo_ready=False)
    assert len(variants) == 1
    assert variants[0]["id"] == "turbo_8"
    assert "xl_sft_24" in skipped


def test_compare_variants_include_all_when_installed() -> None:
    variants, skipped = build_variants(xl_sft_ready=True, xl_turbo_ready=True)
    assert [v["id"] for v in variants] == ["turbo_8", "xl_turbo_8", "xl_sft_24", "xl_sft_50"]
    assert skipped == []
