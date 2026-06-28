"""Tests for the Synthetic Dark Bell v1 LoRA Strength Sweep.

Real ACE generation is never run here.  Tests cover:
  - Gate / is_sweep_enabled
  - SWEEP_STRENGTHS constant contract
  - plan_sweep_groups (pure, no ACE)
  - validate_sweep_lineage
  - _wav_zcr helper
  - run_sweep mandatory-mode raises
  - Report shape (mock)
  - Markdown report structure
  - Studio terminology (no adapter_model, no checkpoint)

The gated end-to-end test is skipped unless SYNTH_LORA_STRENGTH_SWEEP=1.
"""

from __future__ import annotations

import json
import math
import os
import struct
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional  # required for Pydantic forward-ref resolution

import pytest

from app.domain.enums import StyleVersionStatus
from app.domain.style_versions import StyleVersion
from app.domain.training import TrainingRun

StyleVersion.model_rebuild()  # resolve Optional forward refs before creating instances
from app.training.ace_train_commands import LORA_CONFIG_NAME, LORA_WEIGHTS_NAME

from scripts.verify_synthetic_lora_strength_sweep import (
    GATE_ENV,
    MODEL_VERSION_ID,
    SWEEP_DISCLAIMER,
    SWEEP_DURATION,
    SWEEP_PROMPTS,
    SWEEP_SEEDS,
    SWEEP_STRENGTHS,
    TRAINING_RUN_ID,
    is_sweep_enabled,
    plan_sweep_groups,
    run_sweep,
    validate_lora_files,
    validate_sweep_lineage,
    validate_sweep_wav,
    write_report_md,
    _strength_means,
    _wav_spectral_stats,
    _wav_zcr,
    _wav_rms_peak,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _write_test_wav(
    path: Path,
    *,
    freq: float = 440.0,
    duration: float = 1.0,
    sample_rate: int = 48000,
    amplitude: float = 0.5,
) -> None:
    n = int(duration * sample_rate)
    frames = bytearray()
    for i in range(n):
        v = int(amplitude * math.sin(2 * math.pi * freq * i / sample_rate) * 32767)
        frames.extend(struct.pack("<h", max(-32767, min(32767, v))))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(frames))


def _make_run(training_run_id: str = TRAINING_RUN_ID) -> TrainingRun:
    return TrainingRun(
        name="Synthetic Dark Bell v1 LoRA",
        dataset_slice_id="slice_abc",
        backend="ace-step-real",
        base_model_id="acestep-v15-turbo",
        base_model_name="ACE-Step v1.5 Turbo",
        training_mode="lora_finetune",
        artifact_type="lora",
        config_preset="calibration",
        artifact_path="training_runs/train_abc/artifacts/ace_output/final",
    )


def _make_version(run: TrainingRun) -> StyleVersion:
    return StyleVersion(
        name="Dark Bell style",
        training_run_id=run.id,
        dataset_slice_id="slice_abc",
        artifact_path=run.artifact_path,
        backend=run.backend,
        base_model_id=run.base_model_id,
        base_model_name=run.base_model_name,
        training_mode=run.training_mode,
        artifact_type=run.artifact_type,
        status=StyleVersionStatus.CANDIDATE,
    )


def _build_mock_report(tmp_path: Path) -> dict:
    exp_dir = tmp_path / "exp"
    exp_dir.mkdir()
    groups = plan_sweep_groups(exp_dir, str(tmp_path / "final"), lora_available=True)
    return {
        "phase": "synthetic-dark-bell-v1-lora-strength-sweep",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": SWEEP_DISCLAIMER,
        "model_version": {
            "id": MODEL_VERSION_ID,
            "base_model_name": "ACE-Step v1.5 Turbo",
            "training_run_id": TRAINING_RUN_ID,
            "artifact_type": "lora",
        },
        "training_run_id": TRAINING_RUN_ID,
        "lora_load_path": str(tmp_path / "final"),
        "lora_naming": {"ok": True, "files": {}, "lora_dir": str(tmp_path / "final")},
        "lineage_ok": True,
        "lineage_failures": [],
        "sweep_strengths": SWEEP_STRENGTHS,
        "prompts": list(SWEEP_PROMPTS),
        "seeds": list(SWEEP_SEEDS),
        "groups": groups,
        "total_points": 45,
        "generated_count": 0,
        "valid_count": 0,
        "sweep_ok": False,
        "success": False,
        "error": None,
        "report_path": str(exp_dir / "report.json"),
        "report_md_path": str(exp_dir / "report.md"),
    }


# ── Gate tests ─────────────────────────────────────────────────────────────────

class TestSweepGate:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv(GATE_ENV, raising=False)
        assert is_sweep_enabled(False) is False

    def test_enabled_by_flag(self, monkeypatch):
        monkeypatch.delenv(GATE_ENV, raising=False)
        assert is_sweep_enabled(True) is True

    def test_enabled_by_env(self, monkeypatch):
        monkeypatch.setenv(GATE_ENV, "1")
        assert is_sweep_enabled(False) is True

    def test_env_must_be_one(self, monkeypatch):
        monkeypatch.setenv(GATE_ENV, "true")
        assert is_sweep_enabled(False) is False

    def test_raises_when_not_enabled(self, monkeypatch):
        monkeypatch.delenv(GATE_ENV, raising=False)
        from scripts.verify_synthetic_lora_strength_sweep import verify_synthetic_lora_strength_sweep
        with pytest.raises(RuntimeError, match="gated"):
            verify_synthetic_lora_strength_sweep(run_generation=False)


# ── Strength levels ────────────────────────────────────────────────────────────

class TestSweepStrengths:
    def test_five_levels(self):
        assert len(SWEEP_STRENGTHS) == 5

    def test_base_is_zero(self):
        assert SWEEP_STRENGTHS[0] == 0.0

    def test_max_is_one(self):
        assert SWEEP_STRENGTHS[-1] == 1.0

    def test_levels_in_ascending_order(self):
        assert list(SWEEP_STRENGTHS) == sorted(SWEEP_STRENGTHS)

    def test_quarter_step_values_present(self):
        assert 0.25 in SWEEP_STRENGTHS
        assert 0.50 in SWEEP_STRENGTHS
        assert 0.75 in SWEEP_STRENGTHS


# ── plan_sweep_groups ──────────────────────────────────────────────────────────

class TestPlanSweepGroups:
    def test_returns_nine_groups(self, tmp_path):
        groups = plan_sweep_groups(tmp_path, None, lora_available=False)
        assert len(groups) == 9

    def test_five_points_per_group(self, tmp_path):
        groups = plan_sweep_groups(tmp_path, None, lora_available=False)
        for g in groups:
            assert len(g["points"]) == 5

    def test_total_45_points(self, tmp_path):
        groups = plan_sweep_groups(tmp_path, None, lora_available=False)
        assert sum(len(g["points"]) for g in groups) == 45

    def test_covers_all_prompts_and_seeds(self, tmp_path):
        groups = plan_sweep_groups(tmp_path, None, lora_available=False)
        seen = {(g["prompt"], g["seed"]) for g in groups}
        expected = {(p, s) for p in SWEEP_PROMPTS for s in SWEEP_SEEDS}
        assert seen == expected

    def test_group_ids_are_unique(self, tmp_path):
        groups = plan_sweep_groups(tmp_path, None, lora_available=False)
        ids = [g["group_id"] for g in groups]
        assert len(ids) == len(set(ids))

    def test_group_schema(self, tmp_path):
        groups = plan_sweep_groups(tmp_path, None, lora_available=False)
        required = {"group_id", "prompt_index", "seed_index", "prompt", "seed",
                    "duration_seconds", "points"}
        for g in groups:
            assert not (required - set(g)), f"Group missing keys: {required - set(g)}"

    def test_point_schema(self, tmp_path):
        groups = plan_sweep_groups(tmp_path, None, lora_available=False)
        required = {"strength", "use_lora", "lora_path", "lora_scale",
                    "output", "generation_status", "stats"}
        for g in groups:
            for p in g["points"]:
                assert not (required - set(p))

    def test_base_point_has_no_lora(self, tmp_path):
        groups = plan_sweep_groups(tmp_path, "/some/path", lora_available=True)
        for g in groups:
            base = next(p for p in g["points"] if p["strength"] == 0.0)
            assert base["use_lora"] is False
            assert base["lora_path"] is None

    def test_lora_points_have_path_when_available(self, tmp_path):
        lora_path = "/data/runs/abc/final"
        groups = plan_sweep_groups(tmp_path, lora_path, lora_available=True)
        for g in groups:
            for p in g["points"]:
                if p["strength"] > 0.0:
                    assert p["use_lora"] is True
                    assert p["lora_path"] == lora_path

    def test_all_statuses_planned(self, tmp_path):
        groups = plan_sweep_groups(tmp_path, None, lora_available=False)
        for g in groups:
            for p in g["points"]:
                assert p["generation_status"] == "planned"

    def test_output_filenames_include_strength(self, tmp_path):
        groups = plan_sweep_groups(tmp_path, None, lora_available=False)
        for g in groups:
            for p in g["points"]:
                fname = Path(p["output"]).name
                assert f"str{p['strength']:.2f}" in fname

    def test_duration_matches_constant(self, tmp_path):
        groups = plan_sweep_groups(tmp_path, None, lora_available=False)
        for g in groups:
            assert g["duration_seconds"] == SWEEP_DURATION


# ── validate_sweep_lineage ─────────────────────────────────────────────────────

class TestValidateSweepLineage:
    def test_valid_lineage(self):
        run = _make_run()
        version = _make_version(run)
        ok, failures = validate_sweep_lineage(
            version, run, expected_training_run_id=run.id
        )
        assert ok is True
        assert failures == []

    def test_wrong_training_run_id(self):
        run = _make_run()
        version = _make_version(run)
        version = version.model_copy(update={"training_run_id": "wrong_id"})
        ok, failures = validate_sweep_lineage(
            version, run, expected_training_run_id=run.id
        )
        assert ok is False
        assert any("training_run_id" in f for f in failures)

    def test_wrong_model_version_artifact_type(self):
        run = _make_run()
        version = _make_version(run)
        version = version.model_copy(update={"artifact_type": "checkpoint"})
        ok, failures = validate_sweep_lineage(
            version, run, expected_training_run_id=run.id
        )
        assert ok is False
        assert any("artifact_type" in f for f in failures)

    def test_wrong_run_artifact_type(self):
        run = _make_run()
        version = _make_version(run)
        run = run.model_copy(update={"artifact_type": "checkpoint"})
        ok, failures = validate_sweep_lineage(
            version, run, expected_training_run_id=run.id
        )
        assert ok is False
        assert any("artifact_type" in f for f in failures)


# ── WAV ZCR helper ─────────────────────────────────────────────────────────────

class TestWavZCR:
    def test_zcr_high_for_high_freq(self, tmp_path):
        p = tmp_path / "high.wav"
        _write_test_wav(p, freq=10000.0, amplitude=0.5)
        zcr = _wav_zcr(p)
        assert zcr > 0.3, f"Expected high ZCR for 10kHz, got {zcr}"

    def test_zcr_low_for_low_freq(self, tmp_path):
        p = tmp_path / "low.wav"
        _write_test_wav(p, freq=100.0, amplitude=0.5)
        zcr = _wav_zcr(p)
        assert zcr < 0.05, f"Expected low ZCR for 100Hz, got {zcr}"

    def test_zcr_zero_for_silence(self, tmp_path):
        p = tmp_path / "silence.wav"
        _write_test_wav(p, amplitude=0.0)
        zcr = _wav_zcr(p)
        assert zcr == 0.0

    def test_zcr_returns_float(self, tmp_path):
        p = tmp_path / "test.wav"
        _write_test_wav(p, freq=440.0)
        zcr = _wav_zcr(p)
        assert isinstance(zcr, float)

    def test_validate_sweep_wav_includes_zcr(self, tmp_path):
        p = tmp_path / "test.wav"
        _write_test_wav(p, freq=440.0, duration=1.0)
        result = validate_sweep_wav(p)
        assert "zcr" in result
        assert result["zcr"] > 0.0


# ── Spectral stats ─────────────────────────────────────────────────────────────

class TestWavSpectralStats:
    def test_centroid_higher_for_high_freq(self, tmp_path):
        lo = tmp_path / "lo.wav"
        hi = tmp_path / "hi.wav"
        _write_test_wav(lo, freq=200.0, duration=1.0)
        _write_test_wav(hi, freq=8000.0, duration=1.0)
        assert (_wav_spectral_stats(hi)["spectral_centroid"]
                > _wav_spectral_stats(lo)["spectral_centroid"])

    def test_air_ratio_elevated_for_high_freq(self, tmp_path):
        lo = tmp_path / "lo.wav"
        hi = tmp_path / "hi.wav"
        _write_test_wav(lo, freq=200.0, duration=1.0)
        _write_test_wav(hi, freq=10000.0, duration=1.0)
        assert _wav_spectral_stats(hi)["air_ratio"] > _wav_spectral_stats(lo)["air_ratio"]

    def test_rolloff_higher_for_high_freq(self, tmp_path):
        lo = tmp_path / "lo.wav"
        hi = tmp_path / "hi.wav"
        _write_test_wav(lo, freq=100.0, duration=1.0)
        _write_test_wav(hi, freq=9000.0, duration=1.0)
        assert (_wav_spectral_stats(hi)["spectral_rolloff"]
                > _wav_spectral_stats(lo)["spectral_rolloff"])

    def test_presence_plus_air_equals_sum(self, tmp_path):
        p = tmp_path / "tone.wav"
        _write_test_wav(p, freq=4000.0, duration=1.0)
        s = _wav_spectral_stats(p)
        assert abs(s["presence_plus_air"] - (s["presence_ratio"] + s["air_ratio"])) < 1e-6

    def test_band_ratios_sum_at_most_one(self, tmp_path):
        p = tmp_path / "tone.wav"
        _write_test_wav(p, freq=1000.0, duration=1.0)
        s = _wav_spectral_stats(p)
        total = s["low_ratio"] + s["mid_ratio"] + s["presence_ratio"] + s["air_ratio"]
        assert total <= 1.0 + 1e-6

    def test_validate_sweep_wav_includes_spectral_keys(self, tmp_path):
        p = tmp_path / "tone.wav"
        _write_test_wav(p, freq=1000.0, duration=1.0)
        result = validate_sweep_wav(p)
        for key in ("spectral_centroid", "spectral_rolloff",
                    "low_ratio", "mid_ratio", "presence_ratio",
                    "air_ratio", "presence_plus_air"):
            assert key in result, f"Missing key: {key}"

    def test_validate_sweep_wav_missing_file_has_spectral_keys(self, tmp_path):
        result = validate_sweep_wav(tmp_path / "nonexistent.wav")
        for key in ("spectral_centroid", "air_ratio", "presence_plus_air"):
            assert key in result
            assert result[key] == 0.0

    def test_returns_dict_for_missing_file(self, tmp_path):
        s = _wav_spectral_stats(tmp_path / "nonexistent.wav")
        assert isinstance(s, dict)
        assert s.get("spectral_centroid") == 0.0


# ── Strength means helper ──────────────────────────────────────────────────────

class TestStrengthMeans:
    def _groups_with_stats(self, tmp_path: Path) -> list[dict]:
        groups = plan_sweep_groups(tmp_path, str(tmp_path / "final"), lora_available=True)
        rms_val = 0.10
        for g in groups:
            for pt in g["points"]:
                pt["stats"] = {
                    "valid": True, "rms": rms_val + pt["strength"] * 0.05,
                    "zcr": 0.25, "spectral_centroid": 2000.0 + pt["strength"] * 500,
                    "air_ratio": 0.10 + pt["strength"] * 0.02, "presence_plus_air": 0.30,
                }
        return groups

    def test_returns_all_strengths(self, tmp_path):
        groups = self._groups_with_stats(tmp_path)
        means = _strength_means(groups, SWEEP_STRENGTHS)
        assert set(means.keys()) == set(SWEEP_STRENGTHS)

    def test_base_has_n_9(self, tmp_path):
        groups = self._groups_with_stats(tmp_path)
        means = _strength_means(groups, SWEEP_STRENGTHS)
        assert means[0.0]["n"] == 9

    def test_rms_increases_with_strength(self, tmp_path):
        groups = self._groups_with_stats(tmp_path)
        means = _strength_means(groups, SWEEP_STRENGTHS)
        for s in SWEEP_STRENGTHS[1:]:
            assert means[s]["rms"] > means[0.0]["rms"]

    def test_empty_groups_returns_n_zero(self, tmp_path):
        groups = plan_sweep_groups(tmp_path, None, lora_available=False)
        means = _strength_means(groups, SWEEP_STRENGTHS)
        for s in SWEEP_STRENGTHS:
            assert means[s]["n"] == 0


# ── run_sweep mandatory enforcement ───────────────────────────────────────────

class TestRunSweepMandatory:
    def test_raises_mandatory_no_ace(self, tmp_path):
        from unittest.mock import MagicMock
        mock_settings = MagicMock()
        mock_settings.ace_command_template = ""
        mock_settings.ace_enabled = False

        groups = plan_sweep_groups(tmp_path, None, lora_available=False)
        with pytest.raises(RuntimeError, match="Mandatory sweep"):
            run_sweep(groups, mock_settings, mandatory=True)

    def test_raises_mandatory_missing_dir(self, tmp_path):
        from unittest.mock import MagicMock
        mock_settings = MagicMock()
        mock_settings.ace_command_template = "python {script}"
        mock_settings.ace_enabled = True
        mock_settings.ace_step_dir = tmp_path / "nonexistent"

        groups = plan_sweep_groups(tmp_path, None, lora_available=False)
        with pytest.raises(RuntimeError, match="Mandatory sweep"):
            run_sweep(groups, mock_settings, mandatory=True)

    def test_degrades_gracefully_not_mandatory(self, tmp_path):
        from unittest.mock import MagicMock
        mock_settings = MagicMock()
        mock_settings.ace_command_template = ""
        mock_settings.ace_enabled = False

        groups = plan_sweep_groups(tmp_path, None, lora_available=False)
        result = run_sweep(groups, mock_settings, mandatory=False)
        assert len(result) == 9
        for g in result:
            for p in g["points"]:
                assert p["generation_status"] == "skipped_ace_not_configured"

    def test_degrades_preserves_group_count(self, tmp_path):
        from unittest.mock import MagicMock
        mock_settings = MagicMock()
        mock_settings.ace_command_template = ""
        mock_settings.ace_enabled = False

        groups = plan_sweep_groups(tmp_path, None, lora_available=False)
        result = run_sweep(groups, mock_settings, mandatory=False)
        assert sum(len(g["points"]) for g in result) == 45


# ── Report shape ───────────────────────────────────────────────────────────────

class TestSweepReportShape:
    def test_top_level_keys(self, tmp_path):
        report = _build_mock_report(tmp_path)
        required = {
            "phase", "verified_at", "disclaimer", "model_version", "training_run_id",
            "lora_load_path", "lora_naming", "lineage_ok", "lineage_failures",
            "sweep_strengths", "prompts", "seeds", "groups",
            "total_points", "generated_count", "valid_count",
            "sweep_ok", "success", "error",
        }
        missing = required - set(report)
        assert not missing, f"Report missing keys: {missing}"

    def test_nine_groups(self, tmp_path):
        report = _build_mock_report(tmp_path)
        assert len(report["groups"]) == 9

    def test_total_points_is_45(self, tmp_path):
        report = _build_mock_report(tmp_path)
        assert report["total_points"] == 45

    def test_disclaimer_present(self, tmp_path):
        report = _build_mock_report(tmp_path)
        assert report["disclaimer"].strip()

    def test_sweep_strengths_in_report(self, tmp_path):
        report = _build_mock_report(tmp_path)
        assert report["sweep_strengths"] == SWEEP_STRENGTHS

    def test_model_version_artifact_type_is_lora(self, tmp_path):
        report = _build_mock_report(tmp_path)
        assert report["model_version"]["artifact_type"] == "lora"


# ── Markdown report ────────────────────────────────────────────────────────────

class TestSweepMarkdownReport:
    def _get_md(self, tmp_path: Path) -> str:
        report = _build_mock_report(tmp_path)
        md_path = tmp_path / "report.md"
        write_report_md(report, md_path)
        return md_path.read_text(encoding="utf-8")

    def test_md_contains_table_header(self, tmp_path):
        md = self._get_md(tmp_path)
        assert "| Strength |" in md
        assert "| RMS |" in md

    def test_md_contains_checklist(self, tmp_path):
        md = self._get_md(tmp_path)
        assert "Manual Listening Checklist" in md
        assert "Bell clarity" in md

    def test_md_contains_disclaimer(self, tmp_path):
        md = self._get_md(tmp_path)
        assert "does NOT prove automatic quality improvement" in md

    def test_md_contains_score_column(self, tmp_path):
        md = self._get_md(tmp_path)
        assert "Score" in md
        assert "_/_/_/_/_" in md

    def test_md_contains_nine_group_headings(self, tmp_path):
        md = self._get_md(tmp_path)
        count = sum(1 for line in md.splitlines() if line.startswith("### Group p"))
        assert count == 9

    def test_md_has_all_five_strength_rows_per_group(self, tmp_path):
        md = self._get_md(tmp_path)
        # Per-group rows have a backtick-delimited filename after the strength label;
        # the summary table row has a number, so "| 0.00 (base) | `" is unique to group tables.
        assert md.count("| 0.00 (base) | `") == 9  # one per group

    def test_md_no_checkpoint_language(self, tmp_path):
        md = self._get_md(tmp_path)
        lower = md.lower()
        assert "checkpoint" not in lower
        assert "adapter_model" not in lower

    def test_md_has_spectral_summary_section(self, tmp_path):
        md = self._get_md(tmp_path)
        assert "Spectral Summary" in md

    def test_md_summary_table_has_all_strength_rows(self, tmp_path):
        md = self._get_md(tmp_path)
        for s in SWEEP_STRENGTHS:
            assert f"| {s:.2f}" in md

    def test_md_uses_measurable_influence_language(self, tmp_path):
        md = self._get_md(tmp_path)
        assert "measurable influence" in md

    def test_md_uses_candidate_shimmer_language(self, tmp_path):
        md = self._get_md(tmp_path)
        assert "candidate shimmer signal" in md

    def test_md_uses_high_frequency_activity_language(self, tmp_path):
        md = self._get_md(tmp_path)
        assert "high-frequency activity" in md

    def test_md_no_quality_improvement_claims(self, tmp_path):
        md = self._get_md(tmp_path)
        lower = md.lower()
        assert "better" not in lower
        assert "more musical" not in lower
        assert "higher quality" not in lower

    def test_md_per_clip_table_has_centroid_column(self, tmp_path):
        md = self._get_md(tmp_path)
        assert "Centroid Hz" in md

    def test_md_per_clip_table_has_air_ratio_column(self, tmp_path):
        md = self._get_md(tmp_path)
        assert "Air Ratio" in md


# ── Studio terminology ─────────────────────────────────────────────────────────

class TestSweepTerminology:
    def test_artifact_type_constant_is_lora(self, tmp_path):
        report = _build_mock_report(tmp_path)
        assert report["model_version"]["artifact_type"] == "lora"

    def test_no_adapter_model_in_report_keys(self, tmp_path):
        report = _build_mock_report(tmp_path)
        report_json = json.dumps(report)
        # adapter_model must not appear in Studio-facing report (top-level or model_version)
        mv_str = json.dumps(report["model_version"])
        assert "adapter_model" not in mv_str

    def test_no_checkpoint_in_model_version(self, tmp_path):
        report = _build_mock_report(tmp_path)
        mv_str = json.dumps(report["model_version"])
        assert "checkpoint" not in mv_str.lower()

    def test_model_version_key_not_style_version(self, tmp_path):
        report = _build_mock_report(tmp_path)
        # Studio-facing key is "model_version", not "style_version"
        assert "model_version" in report
        assert "style_version" not in report

    def test_lora_weights_name_used_in_lora_naming(self, tmp_path):
        lora_dir = tmp_path / "final"
        lora_dir.mkdir(parents=True)
        (lora_dir / LORA_WEIGHTS_NAME).write_bytes(b"WEIGHTS" * 10)
        (lora_dir / LORA_CONFIG_NAME).write_text("{}", encoding="utf-8")
        result = validate_lora_files(lora_dir)
        assert LORA_WEIGHTS_NAME in result["files"]
        assert LORA_CONFIG_NAME in result["files"]
        assert "adapter_model" not in " ".join(result["files"].keys())


# ── Gated end-to-end ───────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not os.environ.get(GATE_ENV),
    reason=f"Real LoRA generation requires {GATE_ENV}=1",
)
class TestSyntheticLoRAStrengthSweepIntegration:
    def test_full_strength_sweep(self):
        from scripts.verify_synthetic_lora_strength_sweep import verify_synthetic_lora_strength_sweep
        from app.core.config import get_settings
        get_settings.cache_clear()

        report = verify_synthetic_lora_strength_sweep(
            run_generation=True,
            model_version_id=MODEL_VERSION_ID,
            training_run_id=TRAINING_RUN_ID,
        )

        assert report["success"] is True
        assert report["lineage_ok"] is True
        assert report["lora_naming"]["ok"] is True
        assert report["total_points"] == 45
        assert report["generated_count"] == 45
        assert report["valid_count"] == 45
        assert len(report["groups"]) == 9
        assert report["disclaimer"].strip()
        assert Path(report["report_md_path"]).is_file()
