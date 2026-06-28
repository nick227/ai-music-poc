"""Tests for the Synthetic Dark Bell v1 LoRA training flow.

Real ACE training is never run here.  Tests cover:
  - Report structure
  - Artifact normalization (Studio names vs PEFT names)
  - LoRA file naming constants
  - Lineage validation
  - Comparison pair planning
  - Gate / is_flow_enabled logic
  - WAV stat helpers (no ACE required)

The gated end-to-end test is skipped unless SYNTH_LORA_TRAINING_FLOW=1.
"""

from __future__ import annotations

import json
import math
import os
import struct
import wave
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.domain.enums import StyleVersionStatus
from app.domain.models import JobStatus
from app.domain.style_versions import StyleVersion
from app.domain.training import TrainingRun
from app.training.ace_train_commands import (
    LORA_CONFIG_NAME,
    LORA_MANIFEST_NAME,
    LORA_WEIGHTS_NAME,
    PEFT_CONFIG_NAME,
    PEFT_WEIGHTS_NAME,
    normalize_lora_artifact,
)

from scripts.verify_synthetic_lora_training_flow import (
    BASE_MODEL_ID,
    BASE_MODEL_NAME,
    ARTIFACT_TYPE,
    COMPARISON_DISCLAIMER,
    COMPARISON_PROMPTS,
    COMPARISON_SEEDS,
    GATE_ENV,
    TRAINING_MODE,
    is_flow_enabled,
    plan_comparison_pairs,
    run_comparison,
    validate_lora_naming,
    validate_lineage,
    validate_wav_file,
    _all_pairs_succeeded,
    _ffprobe_wav,
    _pair_succeeded,
    _wav_rms_peak,
)


# ── Gate tests ─────────────────────────────────────────────────────────────────

class TestGate:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv(GATE_ENV, raising=False)
        assert is_flow_enabled(False) is False

    def test_enabled_by_flag(self, monkeypatch):
        monkeypatch.delenv(GATE_ENV, raising=False)
        assert is_flow_enabled(True) is True

    def test_enabled_by_env(self, monkeypatch):
        monkeypatch.setenv(GATE_ENV, "1")
        assert is_flow_enabled(False) is True

    def test_env_must_be_one(self, monkeypatch):
        monkeypatch.setenv(GATE_ENV, "true")
        assert is_flow_enabled(False) is False

    def test_raises_when_not_enabled(self, monkeypatch):
        monkeypatch.delenv(GATE_ENV, raising=False)
        from scripts.verify_synthetic_lora_training_flow import verify_synthetic_lora_training_flow
        with pytest.raises(RuntimeError, match="gated"):
            verify_synthetic_lora_training_flow(run_training=False)


# ── LoRA naming constants ──────────────────────────────────────────────────────

class TestLoRaNaming:
    def test_studio_weights_name(self):
        assert LORA_WEIGHTS_NAME == "lora.safetensors"

    def test_studio_config_name(self):
        assert LORA_CONFIG_NAME == "lora_config.json"

    def test_studio_manifest_name(self):
        assert LORA_MANIFEST_NAME == "lora_manifest.json"

    def test_peft_names_differ_from_studio(self):
        assert PEFT_WEIGHTS_NAME != LORA_WEIGHTS_NAME
        assert PEFT_CONFIG_NAME != LORA_CONFIG_NAME

    def test_no_adapter_model_in_studio_names(self):
        assert "adapter_model" not in LORA_WEIGHTS_NAME
        assert "adapter_model" not in LORA_CONFIG_NAME


# ── Artifact normalization ─────────────────────────────────────────────────────

class TestArtifactNormalization:
    def _write_peft(self, final_dir: Path) -> tuple[Path, Path]:
        final_dir.mkdir(parents=True, exist_ok=True)
        peft_config = final_dir / PEFT_CONFIG_NAME
        peft_weights = final_dir / PEFT_WEIGHTS_NAME
        peft_config.write_text(json.dumps({"peft_type": "LORA", "r": 4}), encoding="utf-8")
        peft_weights.write_bytes(b"FAKE_SAFETENSORS_WEIGHTS_DATA" * 10)
        return peft_config, peft_weights

    def test_normalize_creates_studio_files(self, tmp_path):
        final_dir = tmp_path / "final"
        self._write_peft(final_dir)

        result = normalize_lora_artifact(final_dir)
        assert result is not None
        lora_config, lora_weights = result
        assert lora_config.name == LORA_CONFIG_NAME
        assert lora_weights.name == LORA_WEIGHTS_NAME

    def test_studio_files_are_nonzero_after_normalize(self, tmp_path):
        final_dir = tmp_path / "final"
        self._write_peft(final_dir)
        normalize_lora_artifact(final_dir)

        assert (final_dir / LORA_WEIGHTS_NAME).stat().st_size > 0
        assert (final_dir / LORA_CONFIG_NAME).stat().st_size > 0

    def test_peft_files_still_exist_after_normalize(self, tmp_path):
        final_dir = tmp_path / "final"
        self._write_peft(final_dir)
        normalize_lora_artifact(final_dir)

        assert (final_dir / PEFT_WEIGHTS_NAME).is_file()
        assert (final_dir / PEFT_CONFIG_NAME).is_file()

    def test_studio_content_matches_peft(self, tmp_path):
        final_dir = tmp_path / "final"
        peft_config, peft_weights = self._write_peft(final_dir)
        normalize_lora_artifact(final_dir)

        assert (final_dir / LORA_WEIGHTS_NAME).read_bytes() == peft_weights.read_bytes()
        assert (final_dir / LORA_CONFIG_NAME).read_bytes() == peft_config.read_bytes()

    def test_normalize_returns_none_when_no_files(self, tmp_path):
        final_dir = tmp_path / "empty_final"
        final_dir.mkdir()
        result = normalize_lora_artifact(final_dir)
        assert result is None

    def test_normalize_accepts_already_studio_named_files(self, tmp_path):
        final_dir = tmp_path / "final"
        final_dir.mkdir(parents=True)
        (final_dir / LORA_CONFIG_NAME).write_text("{}", encoding="utf-8")
        (final_dir / LORA_WEIGHTS_NAME).write_bytes(b"ALREADY_STUDIO_WEIGHTS")
        result = normalize_lora_artifact(final_dir)
        assert result is not None


# ── validate_lora_naming ───────────────────────────────────────────────────────

class TestValidateLoRaNaming:
    def _make_final_dir(self, tmp_path: Path) -> tuple[Path, Path]:
        """Reproduce the real layout: artifacts/ace_output/final, manifest in artifacts/."""
        artifacts_dir = tmp_path / "artifacts"
        final_dir = artifacts_dir / "ace_output" / "final"
        final_dir.mkdir(parents=True)
        return artifacts_dir, final_dir

    def test_ok_when_files_present(self, tmp_path):
        artifacts_dir, final_dir = self._make_final_dir(tmp_path)
        (final_dir / LORA_WEIGHTS_NAME).write_bytes(b"WEIGHTS" * 10)
        (final_dir / LORA_CONFIG_NAME).write_text("{}", encoding="utf-8")
        (artifacts_dir / LORA_MANIFEST_NAME).write_text("{}", encoding="utf-8")

        result = validate_lora_naming(final_dir)
        assert result["ok"] is True
        assert result["files"][LORA_WEIGHTS_NAME]["exists"] is True
        assert result["files"][LORA_WEIGHTS_NAME]["nonzero"] is True

    def test_not_ok_when_weights_missing(self, tmp_path):
        _, final_dir = self._make_final_dir(tmp_path)
        (final_dir / LORA_CONFIG_NAME).write_text("{}", encoding="utf-8")

        result = validate_lora_naming(final_dir)
        assert result["ok"] is False
        assert result["files"][LORA_WEIGHTS_NAME]["exists"] is False

    def test_not_ok_when_weights_zero_bytes(self, tmp_path):
        _, final_dir = self._make_final_dir(tmp_path)
        (final_dir / LORA_WEIGHTS_NAME).write_bytes(b"")
        (final_dir / LORA_CONFIG_NAME).write_text("{}", encoding="utf-8")

        result = validate_lora_naming(final_dir)
        assert result["ok"] is False
        assert result["files"][LORA_WEIGHTS_NAME]["nonzero"] is False


# ── Lineage validation ─────────────────────────────────────────────────────────

class TestValidateLineage:
    def _make_run(self, dataset_id: str) -> TrainingRun:
        return TrainingRun(
            name="Test LoRA",
            dataset_slice_id=dataset_id,
            backend="ace-step-real",
            base_model_id=BASE_MODEL_ID,
            base_model_name=BASE_MODEL_NAME,
            training_mode=TRAINING_MODE,
            artifact_type=ARTIFACT_TYPE,
            config_preset="calibration",
            artifact_path="training_runs/x/artifacts/ace_output/final",
        )

    def _make_version(self, run: TrainingRun, dataset_id: str) -> StyleVersion:
        return StyleVersion(
            name="Dark Bell style",
            training_run_id=run.id,
            dataset_slice_id=dataset_id,
            artifact_path=run.artifact_path,
            backend=run.backend,
            base_model_id=run.base_model_id,
            base_model_name=run.base_model_name,
            training_mode=run.training_mode,
            artifact_type=run.artifact_type,
            status=StyleVersionStatus.CANDIDATE,
        )

    def _make_dataset(self, dataset_id: str):
        from app.domain.slices import DatasetSlice, DatasetSliceFilter
        from app.domain.enums import DatasetSliceStatus
        return DatasetSlice(
            id=dataset_id,
            name="Dark Bell Dataset",
            slug="dark-bell-dataset",
            filter=DatasetSliceFilter(category_ids=["cat_instrument_bell"]),
            media_ids=[],
            status=DatasetSliceStatus.READY,
        )

    def test_valid_lineage(self):
        ds_id = "slice_test_001"
        dataset = self._make_dataset(ds_id)
        run = self._make_run(ds_id)
        version = self._make_version(run, ds_id)

        ok, failures = validate_lineage(run, version, dataset)
        assert ok is True
        assert failures == []

    def test_wrong_training_run_id(self):
        ds_id = "slice_test_002"
        dataset = self._make_dataset(ds_id)
        run = self._make_run(ds_id)
        version = self._make_version(run, ds_id)
        version = version.model_copy(update={"training_run_id": "wrong_run_id"})

        ok, failures = validate_lineage(run, version, dataset)
        assert ok is False
        assert any("training_run_id" in f for f in failures)

    def test_wrong_dataset_id(self):
        ds_id = "slice_test_003"
        dataset = self._make_dataset(ds_id)
        run = self._make_run("different_dataset_id")
        version = self._make_version(run, "different_dataset_id")

        ok, failures = validate_lineage(run, version, dataset)
        assert ok is False

    def test_wrong_base_model(self):
        ds_id = "slice_test_004"
        dataset = self._make_dataset(ds_id)
        run = self._make_run(ds_id)
        version = self._make_version(run, ds_id)
        version = version.model_copy(update={"base_model_name": "wrong-model"})

        ok, failures = validate_lineage(run, version, dataset)
        assert ok is False
        assert any("base_model_name" in f for f in failures)

    def test_wrong_training_mode(self):
        ds_id = "slice_test_005"
        dataset = self._make_dataset(ds_id)
        run = self._make_run(ds_id)
        version = self._make_version(run, ds_id)
        version = version.model_copy(update={"training_mode": "full_finetune"})

        ok, failures = validate_lineage(run, version, dataset)
        assert ok is False
        assert any("training_mode" in f for f in failures)

    def test_wrong_artifact_type(self):
        ds_id = "slice_test_006"
        dataset = self._make_dataset(ds_id)
        run = self._make_run(ds_id)
        version = self._make_version(run, ds_id)
        version = version.model_copy(update={"artifact_type": "checkpoint"})

        ok, failures = validate_lineage(run, version, dataset)
        assert ok is False
        assert any("artifact_type" in f for f in failures)


# ── Comparison pair planning ───────────────────────────────────────────────────

class TestComparisonPairPlanning:
    def test_returns_nine_pairs(self, tmp_path):
        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        assert len(pairs) == 9

    def test_covers_all_prompts_and_seeds(self, tmp_path):
        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        for prompt in COMPARISON_PROMPTS:
            assert any(p["prompt"] == prompt for p in pairs)
        for seed in COMPARISON_SEEDS:
            assert any(p["seed"] == seed for p in pairs)

    def test_all_prompts_x_all_seeds(self, tmp_path):
        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        seen = {(p["prompt"], p["seed"]) for p in pairs}
        expected = {(prompt, seed) for prompt in COMPARISON_PROMPTS for seed in COMPARISON_SEEDS}
        assert seen == expected

    def test_pair_ids_are_unique(self, tmp_path):
        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        ids = [p["pair_id"] for p in pairs]
        assert len(ids) == len(set(ids))

    def test_pair_schema(self, tmp_path):
        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        required = {"pair_id", "prompt", "seed", "base_output", "lora_output",
                    "lora_path", "generation_status", "duration_seconds"}
        for pair in pairs:
            missing = required - set(pair)
            assert not missing, f"Pair missing keys: {missing}"

    def test_status_is_planned(self, tmp_path):
        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        for pair in pairs:
            assert pair["generation_status"] == "planned"

    def test_lora_path_none_when_unavailable(self, tmp_path):
        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        for pair in pairs:
            assert pair["lora_path"] is None

    def test_lora_path_set_when_available(self, tmp_path):
        lora_dir = tmp_path / "final"
        lora_dir.mkdir()
        pairs = plan_comparison_pairs(tmp_path, lora_dir, lora_available=True)
        for pair in pairs:
            assert pair["lora_path"] == str(lora_dir)

    def test_outputs_under_experiment_dir(self, tmp_path):
        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        for pair in pairs:
            assert Path(pair["base_output"]).parent == tmp_path
            assert Path(pair["lora_output"]).parent == tmp_path

    def test_duration_matches_constant(self, tmp_path):
        from scripts.verify_synthetic_lora_training_flow import COMPARISON_DURATION_SECONDS
        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        for pair in pairs:
            assert pair["duration_seconds"] == COMPARISON_DURATION_SECONDS


# ── Report structure ───────────────────────────────────────────────────────────

class TestReportStructure:
    """Validate the contract of the report dict without running real training."""

    def _build_mock_report(self, tmp_path: Path) -> dict:
        experiment_dir = tmp_path / "exp"
        experiment_dir.mkdir()
        pairs = plan_comparison_pairs(experiment_dir, None, lora_available=False)
        return {
            "phase": "synthetic-dark-bell-v1-lora-training-flow",
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "disclaimer": COMPARISON_DISCLAIMER,
            "dataset": {
                "slice_id": "slice_abc",
                "name": "Dark Bell Dataset",
                "status": "READY",
                "manifest_path": "/data/slices/abc/manifest.json",
                "manifest_hash": "deadbeef" * 8,
                "manifest_file_hash_before": "cafebabe" * 8,
                "manifest_file_hash_after": "cafebabe" * 8,
                "immutable_after_training": True,
            },
            "training_run": {
                "id": "train_abc",
                "status": "SUCCEEDED",
                "backend": "ace-step-real",
                "base_model_name": BASE_MODEL_NAME,
                "base_model_id": BASE_MODEL_ID,
                "training_mode": TRAINING_MODE,
                "artifact_type": ARTIFACT_TYPE,
                "artifact_path": "training_runs/train_abc/artifacts/ace_output/final",
                "style_version_id": "style_abc",
                "error": None,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
            "command": ["python", "scripts/ace_train_runner.py"],
            "stdout_log": str(tmp_path / "stdout.log"),
            "stderr_log": str(tmp_path / "stderr.log"),
            "train_log": str(tmp_path / "train.log"),
            "start_time": datetime.now(timezone.utc).isoformat(),
            "end_time": datetime.now(timezone.utc).isoformat(),
            "returncode": 0,
            "lora_naming": {"ok": True, "files": {}, "final_dir": str(tmp_path)},
            "lora_manifest_path": str(tmp_path / "lora_manifest.json"),
            "model_version": {
                "id": "style_abc",
                "created": True,
                "lineage_ok": True,
                "lineage_failures": [],
            },
            "comparison": {
                "prompts": COMPARISON_PROMPTS,
                "seeds": COMPARISON_SEEDS,
                "pairs": pairs,
                "disclaimer": COMPARISON_DISCLAIMER,
            },
            "produced_files": [],
            "comparison_ok": True,
            "comparison_error": None,
            "success": True,
            "error": None,
            "report_path": str(experiment_dir / "report.json"),
        }

    def test_top_level_keys(self, tmp_path):
        report = self._build_mock_report(tmp_path)
        required = {
            "phase", "verified_at", "disclaimer", "dataset", "training_run",
            "command", "returncode", "lora_naming", "lora_manifest_path",
            "model_version", "comparison", "produced_files",
            "comparison_ok", "comparison_error", "success", "error",
        }
        missing = required - set(report)
        assert not missing, f"Report missing top-level keys: {missing}"

    def test_training_run_keys(self, tmp_path):
        report = self._build_mock_report(tmp_path)
        required = {"id", "status", "backend", "base_model_name", "training_mode", "artifact_type"}
        missing = required - set(report["training_run"])
        assert not missing

    def test_model_version_keys(self, tmp_path):
        report = self._build_mock_report(tmp_path)
        required = {"id", "created", "lineage_ok", "lineage_failures"}
        missing = required - set(report["model_version"])
        assert not missing

    def test_comparison_keys(self, tmp_path):
        report = self._build_mock_report(tmp_path)
        required = {"prompts", "seeds", "pairs", "disclaimer"}
        missing = required - set(report["comparison"])
        assert not missing

    def test_disclaimer_present_and_non_empty(self, tmp_path):
        report = self._build_mock_report(tmp_path)
        assert report["disclaimer"].strip()
        assert report["comparison"]["disclaimer"].strip()

    def test_training_mode_is_lora_finetune(self, tmp_path):
        report = self._build_mock_report(tmp_path)
        assert report["training_run"]["training_mode"] == "lora_finetune"

    def test_artifact_type_is_lora(self, tmp_path):
        report = self._build_mock_report(tmp_path)
        assert report["training_run"]["artifact_type"] == "lora"

    def test_base_model_name_correct(self, tmp_path):
        report = self._build_mock_report(tmp_path)
        assert report["training_run"]["base_model_name"] == "ACE-Step v1.5 Turbo"

    def test_no_adapter_model_terminology_in_training_run(self, tmp_path):
        report = self._build_mock_report(tmp_path)
        run = report["training_run"]
        # Studio artifact names must not expose PEFT/adapter_model names
        for key in ("artifact_path", "artifact_type", "training_mode"):
            assert "adapter_model" not in str(run.get(key) or ""), \
                f"training_run[{key!r}] must not reference adapter_model"
        assert run["artifact_type"] != "checkpoint"

    def test_no_adapter_model_in_lora_naming_keys(self, tmp_path):
        report = self._build_mock_report(tmp_path)
        naming_keys = list(report["lora_naming"].get("files", {}).keys())
        for key in naming_keys:
            assert "adapter_model" not in key, \
                f"lora_naming file key {key!r} must not use adapter_model name"


# ── WAV stat helpers ───────────────────────────────────────────────────────────

class TestWavStats:
    def _write_test_wav(self, path: Path, *, freq: float = 440.0, duration: float = 1.0,
                         sample_rate: int = 48000, amplitude: float = 0.5) -> None:
        import math
        n = int(duration * sample_rate)
        frames = bytearray()
        for i in range(n):
            t = i / sample_rate
            v = int(amplitude * math.sin(2 * math.pi * freq * t) * 32767)
            frames.extend(struct.pack("<h", max(-32767, min(32767, v))))
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(bytes(frames))

    def test_rms_peak_sine_wave(self, tmp_path):
        p = tmp_path / "sine.wav"
        self._write_test_wav(p, amplitude=0.5)
        stats = _wav_rms_peak(p)
        # Sine wave: peak ≈ 0.5, RMS ≈ 0.5 / sqrt(2) ≈ 0.3535
        assert abs(stats["peak"] - 0.5) < 0.02
        assert abs(stats["rms"] - 0.5 / math.sqrt(2)) < 0.02

    def test_rms_peak_silence(self, tmp_path):
        p = tmp_path / "silence.wav"
        self._write_test_wav(p, amplitude=0.0)
        stats = _wav_rms_peak(p)
        assert stats["rms"] == 0.0
        assert stats["peak"] == 0.0

    def test_validate_wav_file_missing(self, tmp_path):
        result = validate_wav_file(tmp_path / "nonexistent.wav")
        assert result["exists"] is False
        assert result["valid"] is False

    def test_validate_wav_file_exists(self, tmp_path):
        p = tmp_path / "test.wav"
        self._write_test_wav(p, duration=2.0)
        result = validate_wav_file(p)
        assert result["exists"] is True
        assert result["peak"] > 0.0
        assert result["rms"] > 0.0

    def test_validate_wav_file_path_in_result(self, tmp_path):
        p = tmp_path / "test.wav"
        self._write_test_wav(p)
        result = validate_wav_file(p)
        assert result["path"] == str(p)


# ── Mandatory comparison enforcement ──────────────────────────────────────────

class TestMandatoryComparison:
    """Prove gated real mode cannot pass when comparison pairs stay planned/skipped."""

    def test_planned_pair_fails_pair_succeeded(self, tmp_path):
        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        for pair in pairs:
            assert _pair_succeeded(pair) is False, \
                f"Planned pair should fail succeeded check: {pair['pair_id']}"

    def test_skipped_pair_fails_pair_succeeded(self, tmp_path):
        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        skipped = [dict(p, generation_status="skipped_ace_not_configured") for p in pairs]
        for pair in skipped:
            assert _pair_succeeded(pair) is False

    def test_succeeded_pair_with_valid_base_passes(self, tmp_path):
        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        ok = dict(pairs[0], generation_status="succeeded", base_stats={"valid": True})
        assert _pair_succeeded(ok) is True

    def test_succeeded_pair_fails_when_lora_expected_but_stats_missing(self, tmp_path):
        lora_dir = tmp_path / "final"
        lora_dir.mkdir()
        pairs = plan_comparison_pairs(tmp_path, lora_dir, lora_available=True)
        pair = dict(pairs[0], generation_status="succeeded",
                    base_stats={"valid": True}, lora_stats=None)
        assert _pair_succeeded(pair) is False

    def test_all_pairs_succeeded_true_when_all_pass(self, tmp_path):
        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        succeeded = [
            dict(p, generation_status="succeeded", base_stats={"valid": True})
            for p in pairs
        ]
        assert _all_pairs_succeeded(succeeded) is True

    def test_all_pairs_succeeded_false_when_one_planned(self, tmp_path):
        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        mixed = [
            dict(p, generation_status="succeeded", base_stats={"valid": True})
            for p in pairs
        ]
        mixed[4] = dict(pairs[4])  # leave one as planned (no base_stats)
        assert _all_pairs_succeeded(mixed) is False

    def test_run_comparison_raises_mandatory_no_ace(self, tmp_path):
        from unittest.mock import MagicMock
        mock_settings = MagicMock()
        mock_settings.ace_command_template = ""
        mock_settings.ace_enabled = False

        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        with pytest.raises(RuntimeError, match="Mandatory comparison"):
            run_comparison(pairs, mock_settings, None, mandatory=True)

    def test_run_comparison_raises_mandatory_missing_dir(self, tmp_path):
        from unittest.mock import MagicMock
        mock_settings = MagicMock()
        mock_settings.ace_command_template = "python {script}"
        mock_settings.ace_enabled = True
        mock_settings.ace_step_dir = tmp_path / "nonexistent"

        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        with pytest.raises(RuntimeError, match="Mandatory comparison"):
            run_comparison(pairs, mock_settings, None, mandatory=True)

    def test_run_comparison_degrades_gracefully_not_mandatory(self, tmp_path):
        from unittest.mock import MagicMock
        mock_settings = MagicMock()
        mock_settings.ace_command_template = ""
        mock_settings.ace_enabled = False

        pairs = plan_comparison_pairs(tmp_path, None, lora_available=False)
        result = run_comparison(pairs, mock_settings, None, mandatory=False)
        assert all(p["generation_status"] == "skipped_ace_not_configured" for p in result)
        assert len(result) == 9


# ── Gated end-to-end test ──────────────────────────────────────────────────────

@pytest.mark.skipif(
    not os.environ.get(GATE_ENV),
    reason=f"Real LoRA training requires {GATE_ENV}=1",
)
class TestSyntheticLoRATrainingFlowIntegration:
    def test_full_lora_training_flow(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        from app.core.config import get_settings
        get_settings.cache_clear()

        from scripts.verify_synthetic_lora_training_flow import verify_synthetic_lora_training_flow
        report = verify_synthetic_lora_training_flow(
            run_training=True,
            pack_dir=tmp_path / "synthetic_audio" / "dark-bell-v1",
            clip_count=15,
            min_dur=4.5,
            max_dur=6.0,
        )

        assert report["success"] is True
        assert report["training_run"]["status"] == "SUCCEEDED"
        assert report["lora_naming"]["ok"] is True
        assert report["model_version"]["created"] is True
        assert report["model_version"]["lineage_ok"] is True
        assert report["dataset"]["immutable_after_training"] is True
        assert len(report["comparison"]["pairs"]) == 9
        assert report["disclaimer"].strip()
