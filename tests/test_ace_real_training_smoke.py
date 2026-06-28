from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.domain.models import JobStatus
from app.domain.training import TrainingRun
from scripts.verify_ace_real_training_smoke import (
    GATE_ENV,
    build_report_payload,
    real_training_smoke_enabled,
    validate_adapter_artifact,
)
from scripts.verify_mock_training_lineage_flow import ARTIFACT_TYPE, BASE_MODEL_NAME, TRAINING_MODE


def test_real_training_smoke_gate_requires_flag_or_env() -> None:
    assert real_training_smoke_enabled(False, {}) is False
    assert real_training_smoke_enabled(False, {GATE_ENV: "0"}) is False
    assert real_training_smoke_enabled(False, {GATE_ENV: "1"}) is True
    assert real_training_smoke_enabled(True, {}) is True


def test_validate_adapter_artifact_requires_expected_nonzero_files(tmp_path: Path) -> None:
    final_dir = tmp_path / "artifacts" / "ace_output" / "final"
    missing = validate_adapter_artifact(final_dir)
    assert missing["ok"] is False
    assert missing["artifact_dir_exists"] is False

    final_dir.mkdir(parents=True)
    (final_dir / "lora_config.json").write_text("{}", encoding="utf-8")
    (final_dir / "lora.safetensors").write_bytes(b"tiny-real-smoke-fixture")

    valid = validate_adapter_artifact(final_dir)
    assert valid["ok"] is True
    assert valid["expected_files"]["lora_config.json"]["nonzero"] is True
    assert valid["expected_files"]["lora.safetensors"]["nonzero"] is True


def test_validate_adapter_artifact_accepts_legacy_peft_names(tmp_path: Path) -> None:
    final_dir = tmp_path / "legacy" / "final"
    final_dir.mkdir(parents=True)
    (final_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
    (final_dir / "adapter_model.safetensors").write_bytes(b"legacy")

    valid = validate_adapter_artifact(final_dir)
    assert valid["ok"] is True
    assert valid["legacy_peft_files_accepted"] is True


def test_build_report_payload_requires_success_artifact_and_model_version(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    run = TrainingRun(
        id="train_phase4",
        name="Phase 4",
        dataset_slice_id="slice_bell_ready",
        backend="ace-step-real-smoke",
        base_model_id=BASE_MODEL_NAME,
        base_model_name=BASE_MODEL_NAME,
        training_mode=TRAINING_MODE,
        artifact_type=ARTIFACT_TYPE,
        config_preset="calibration",
        status=JobStatus.SUCCEEDED,
        artifact_path="training_runs/train_phase4/artifacts/ace_output/final",
        started_at=now,
        finished_at=now,
    )
    phase3 = {
        "report_path": str(tmp_path / "phase3.json"),
        "frozen_manifest_hash": "manifest-logical-hash",
        "source_media_ids": ["media_bell"],
        "source_file_paths": ["/tmp/bell.wav"],
        "workspace_path": str(tmp_path / "workspace"),
    }
    artifact_validation = {"ok": True, "artifact_dir_exists": True, "expected_files": {}}

    report = build_report_payload(
        phase3=phase3,
        run=run,
        command=["/home/administrator/models/ACE-Step-1.5/.venv/bin/python", "scripts/ace_train_runner.py"],
        stdout_path=tmp_path / "stdout.log",
        stderr_path=tmp_path / "stderr.log",
        train_log_path=tmp_path / "train.log",
        start_time=now.isoformat(),
        end_time=now.isoformat(),
        returncode=0,
        runtime_profile={"gpu": "test"},
        artifact_validation=artifact_validation,
        produced_files=[],
        manifest_hash_before="frozen-file-hash",
        manifest_hash_after="frozen-file-hash",
        model_version_id="style_real_smoke",
        error=None,
    )

    assert report["success"] is True
    assert report["model_version_created"] is True
    assert report["training_run"]["model_version_id"] == "style_real_smoke"
    assert report["frozen_manifest_immutable"] is True

    failed = build_report_payload(
        phase3=phase3,
        run=run.model_copy(update={"status": JobStatus.FAILED, "artifact_path": None, "error": "boom"}),
        command=["python"],
        stdout_path=tmp_path / "stdout.log",
        stderr_path=tmp_path / "stderr.log",
        train_log_path=tmp_path / "train.log",
        start_time=now.isoformat(),
        end_time=now.isoformat(),
        returncode=1,
        runtime_profile={},
        artifact_validation={"ok": False},
        produced_files=[],
        manifest_hash_before="frozen-file-hash",
        manifest_hash_after="frozen-file-hash",
        model_version_id=None,
        error="boom",
    )

    assert failed["success"] is False
    assert failed["model_version_created"] is False
