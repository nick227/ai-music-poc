from __future__ import annotations

import wave
from pathlib import Path

from scripts.verify_ace_model_version_comparison import (
    build_generation_pairs,
    slugify,
    validate_adapter_package,
    validate_generated_audio,
)


def test_build_generation_pairs_are_paired_by_prompt_and_seed() -> None:
    pairs = build_generation_pairs(prompts=["Soft Bell!"], seeds=[101, 202])
    assert [pair["seed"] for pair in pairs] == [101, 202]
    assert all(pair["prompt"] == "Soft Bell!" for pair in pairs)
    assert pairs[0]["stem"].startswith("p01-seed-101-soft-bell")


def test_slugify_returns_stable_safe_filename_piece() -> None:
    slug = slugify("Dreamy ambient soundscape with small bell accents")
    assert slug.startswith("dreamy-ambient-soundscape-with-small-bell")
    assert len(slug) <= 48
    assert slugify("!!!") == "prompt"


def test_validate_adapter_package_requires_manifest_and_adapter_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "training_runs" / "train_ok"
    adapter_dir = run_dir / "artifacts" / "ace_output" / "final"
    adapter_dir.mkdir(parents=True)
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
    (adapter_dir / "adapter_model.safetensors").write_bytes(b"adapter")

    missing_manifest = validate_adapter_package(adapter_dir, run_dir)
    assert missing_manifest["ok"] is False

    (run_dir / "artifacts" / "artifact_manifest.json").write_text("{}", encoding="utf-8")
    valid = validate_adapter_package(adapter_dir, run_dir)
    assert valid["ok"] is True
    assert valid["files"]["adapter_model.safetensors"]["nonzero"] is True


def test_validate_generated_audio_reports_rms_peak_and_duration(tmp_path: Path) -> None:
    path = tmp_path / "short.wav"
    sample_rate = 16000
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = bytearray()
        for index in range(sample_rate):
            sample = 12000 if index % 2 == 0 else -12000
            frames.extend(int(sample).to_bytes(2, "little", signed=True))
        handle.writeframes(bytes(frames))

    stats = validate_generated_audio(path, min_duration_seconds=0.5)
    assert stats["ok"] is True
    assert stats["duration_seconds"] >= 1.0
    assert stats["file_size_bytes"] > 0
    assert stats["rms"] > 0
    assert stats["peak_abs_sample"] == 12000
