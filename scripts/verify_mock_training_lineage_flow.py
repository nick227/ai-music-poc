#!/usr/bin/env python3
"""Verify Phase 2 frozen fixture dataset -> mock training -> Model Version lineage."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

from app.core.config import get_settings
from app.domain.enums import DatasetSliceStatus, StyleVersionStatus
from app.domain.models import JobStatus
from app.domain.training import TrainingRun
from app.domain.training_presets import resolve_training_preset
from app.services.style_version_service import StyleVersionService
from app.storage.slice_store import SliceStore
from app.storage.style_version_store import StyleVersionStore
from app.storage.training_run_store import TrainingRunStore
from scripts.verify_fixture_dataset_flow import verify_fixture_dataset_flow


BASE_MODEL_ID = "acestep-v15-turbo"
BASE_MODEL_NAME = "ACE-Step v1.5 Turbo"
TRAINING_MODE = "lora_finetune"
ARTIFACT_TYPE = "lora"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_runtime_profile(settings) -> dict:
    path = settings.data_dir / "ace_hardware_profile.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_mock_artifact(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")
    # This is intentionally a fake adapter file with stable binary-ish content.
    path.write_bytes(b"MOCK_LORA_ADAPTER\n" + encoded)


def verify_mock_training_lineage_flow() -> dict:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()

    phase1 = verify_fixture_dataset_flow()
    bell_dataset_id = phase1["frozen_dataset"]["slice_id"]

    slice_store = SliceStore(settings.slices_dir)
    bell_dataset = slice_store.get(bell_dataset_id)
    if bell_dataset is None:
        raise RuntimeError(f"Frozen Bell dataset not found: {bell_dataset_id}")
    if bell_dataset.status != DatasetSliceStatus.READY:
        raise RuntimeError(f"Bell dataset is not READY: {bell_dataset.status}")

    manifest_path = settings.slices_dir / bell_dataset.id / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"Bell dataset manifest not found: {manifest_path}")
    manifest_before_text = manifest_path.read_text(encoding="utf-8")
    manifest_before_file_hash = _sha256(manifest_path)
    manifest = json.loads(manifest_before_text)
    manifest_hash = manifest.get("manifest_hash")
    if not manifest_hash:
        raise RuntimeError("Bell dataset manifest has no manifest_hash")

    runtime_profile = _load_runtime_profile(settings)
    config = resolve_training_preset("calibration")
    config.update(
        {
            "evidence_phase": "phase-2-mock-training-lineage",
            "dataset_manifest_hash": manifest_hash,
            "runtime_profile": runtime_profile,
            "real_ace_training": False,
        }
    )

    now = datetime.now(timezone.utc)
    run = TrainingRun(
        name="Bell fixture mock LoRA evidence",
        dataset_slice_id=bell_dataset.id,
        backend="mock-training-evidence",
        base_model_id=BASE_MODEL_ID,
        base_model_name=BASE_MODEL_NAME,
        training_mode=TRAINING_MODE,
        artifact_type=ARTIFACT_TYPE,
        config_preset="calibration",
        config=config,
        status=JobStatus.RUNNING,
        started_at=now,
        created_at=now,
        updated_at=now,
    )

    run_store = TrainingRunStore(settings.training_runs_dir)
    run_store.save(run)
    run_store.write_config(run.id, config)
    run_store.append_log(run.id, "phase 2 evidence: mock training started")

    artifact_rel = f"training_runs/{run.id}/artifacts/lora.safetensors"
    artifact_path = settings.data_dir / artifact_rel
    artifact_payload = {
        "format": "mock-lora-adapter",
        "training_run_id": run.id,
        "dataset_slice_id": bell_dataset.id,
        "dataset_manifest_hash": manifest_hash,
        "base_model_name": BASE_MODEL_NAME,
        "base_model_id": BASE_MODEL_ID,
        "training_mode": TRAINING_MODE,
        "artifact_type": ARTIFACT_TYPE,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_mock_artifact(artifact_path, artifact_payload)

    artifact_manifest = {
        "artifact_type": ARTIFACT_TYPE,
        "artifact_path": "lora.safetensors",
        "load_path": str(artifact_path.resolve()),
        "lora_path": str(artifact_path.resolve()),
        "training_run_id": run.id,
        "dataset_slice_id": bell_dataset.id,
        "dataset_manifest_hash": manifest_hash,
        "base_model_name": BASE_MODEL_NAME,
        "training_mode": TRAINING_MODE,
    }
    artifact_manifest_path = run_store.artifacts_dir(run.id) / "lora_manifest.json"
    artifact_manifest_path.write_text(json.dumps(artifact_manifest, indent=2), encoding="utf-8")
    legacy_manifest_path = run_store.artifacts_dir(run.id) / "artifact_manifest.json"
    legacy_manifest_path.write_text(json.dumps(artifact_manifest, indent=2), encoding="utf-8")

    finished_at = datetime.now(timezone.utc)
    run = run.model_copy(
        update={
            "status": JobStatus.SUCCEEDED,
            "artifact_path": artifact_rel,
            "finished_at": finished_at,
            "updated_at": finished_at,
            "error": None,
        }
    )
    run_store.save(run)
    run_store.append_log(run.id, f"phase 2 evidence: wrote mock artifact {artifact_rel}")
    run_store.append_log(run.id, "phase 2 evidence: mock training succeeded")

    style_service = StyleVersionService(StyleVersionStore(settings.style_versions_dir))
    model_version = style_service.create_from_run(
        run,
        bell_dataset.name,
        status=StyleVersionStatus.CANDIDATE,
    )
    run = run.model_copy(update={"style_version_id": model_version.id, "updated_at": datetime.now(timezone.utc)})
    run_store.save(run)
    run_store.append_log(run.id, f"phase 2 evidence: registered model version {model_version.id}")

    manifest_after_text = manifest_path.read_text(encoding="utf-8")
    manifest_after_file_hash = _sha256(manifest_path)
    artifact_exists = artifact_path.is_file()
    lineage_ok = (
        model_version.training_run_id == run.id
        and run.dataset_slice_id == bell_dataset.id
        and model_version.dataset_slice_id == bell_dataset.id
        and model_version.base_model_name == BASE_MODEL_NAME
        and model_version.training_mode == TRAINING_MODE
        and model_version.artifact_type == ARTIFACT_TYPE
        and artifact_exists
        and manifest_before_text == manifest_after_text
    )
    if not lineage_ok:
        raise RuntimeError("Mock training lineage verification failed")

    report = {
        "phase": "phase-2-mock-training-lineage-flow",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "phase1_report_path": phase1.get("report_path"),
        "dataset": {
            "slice_id": bell_dataset.id,
            "name": bell_dataset.name,
            "status": bell_dataset.status.value,
            "manifest_path": str(manifest_path),
            "manifest_hash": manifest_hash,
            "manifest_file_hash_before": manifest_before_file_hash,
            "manifest_file_hash_after": manifest_after_file_hash,
            "immutable_after_mock_training": manifest_before_text == manifest_after_text,
        },
        "training_run": {
            "id": run.id,
            "status": run.status.value,
            "dataset_slice_id": run.dataset_slice_id,
            "base_model_name": run.base_model_name,
            "training_mode": run.training_mode,
            "artifact_type": run.artifact_type,
            "artifact_path": run.artifact_path,
            "artifact_exists": artifact_exists,
            "config_path": str(settings.training_runs_dir / run.id / "config.json"),
            "logs_path": str(run_store.log_path(run.id)),
        },
        "model_version": {
            "id": model_version.id,
            "training_run_id": model_version.training_run_id,
            "dataset_slice_id": model_version.dataset_slice_id,
            "base_model_name": model_version.base_model_name,
            "training_mode": model_version.training_mode,
            "artifact_type": model_version.artifact_type,
            "artifact_path": model_version.artifact_path,
            "status": model_version.status.value,
        },
        "runtime_profile_present": bool(runtime_profile),
        "success": True,
    }
    report_dir = settings.data_dir / "experiments" / "mock-training-lineage-flow"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 2 mock training lineage flow")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = verify_mock_training_lineage_flow()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        run = report["training_run"]
        version = report["model_version"]
        dataset = report["dataset"]
        print("Mock training lineage flow: PASS")
        print(f"Frozen Bell dataset: {dataset['slice_id']} manifest={dataset['manifest_hash']}")
        print(f"Training run: {run['id']} status={run['status']} artifact={run['artifact_path']}")
        print(f"Model version: {version['id']} status={version['status']}")
        print(f"Lineage: {version['id']} -> {run['id']} -> {dataset['slice_id']}")
        print(f"Report: {report['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
