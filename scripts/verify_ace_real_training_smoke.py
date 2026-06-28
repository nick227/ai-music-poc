#!/usr/bin/env python3
"""Optional Phase 4 proof: run a tiny real ACE fine-tuning smoke test."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
from app.services.slice_service import SliceService
from app.services.style_version_service import StyleVersionService
from app.storage.slice_store import SliceStore
from app.storage.style_version_store import StyleVersionStore
from app.storage.training_run_store import TrainingRunStore
from app.training.ace_train_commands import required_adapter_files, run_adapter_final_dir
from scripts.verify_ace_training_contract_flow import _absolute_no_symlink, _services, verify_ace_training_contract_flow
from scripts.verify_mock_training_lineage_flow import ARTIFACT_TYPE, BASE_MODEL_NAME, TRAINING_MODE

GATE_ENV = "ACE_REAL_TRAINING_SMOKE"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def real_training_smoke_enabled(flag_enabled: bool, env: dict[str, str] | None = None) -> bool:
    values = os.environ if env is None else env
    return flag_enabled or values.get(GATE_ENV, "").strip() == "1"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_runtime_profile(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "ace_hardware_profile.json"
    if not path.is_file():
        return {}
    try:
        return _read_json(path)
    except json.JSONDecodeError:
        return {}


def _relative_to_data(path: Path, data_dir: Path) -> str:
    try:
        return str(path.resolve().relative_to(data_dir.resolve()))
    except ValueError:
        return str(path.resolve())


def collect_produced_files(run_dir: Path) -> list[dict[str, Any]]:
    if not run_dir.exists():
        return []
    files: list[dict[str, Any]] = []
    for path in sorted(item for item in run_dir.rglob("*") if item.is_file()):
        files.append(
            {
                "path": str(path),
                "relative_path": str(path.relative_to(run_dir)),
                "size_bytes": path.stat().st_size,
            }
        )
    return files


def validate_adapter_artifact(final_dir: Path) -> dict[str, Any]:
    config_path, weights_path = required_adapter_files(final_dir)
    expected_files: dict[str, dict[str, Any]] = {}
    for path in (config_path, weights_path):
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
        expected_files[path.name] = {
            "path": str(path),
            "exists": exists,
            "size_bytes": size,
            "nonzero": size > 0,
        }
    return {
        "artifact_dir": str(final_dir),
        "artifact_dir_exists": final_dir.is_dir(),
        "expected_files": expected_files,
        "ok": final_dir.is_dir() and all(item["exists"] and item["nonzero"] for item in expected_files.values()),
    }


def build_report_payload(
    *,
    phase3: dict[str, Any],
    run: TrainingRun,
    command: list[str],
    stdout_path: Path,
    stderr_path: Path,
    train_log_path: Path,
    start_time: str | None,
    end_time: str | None,
    returncode: int | None,
    runtime_profile: dict[str, Any],
    artifact_validation: dict[str, Any],
    produced_files: list[dict[str, Any]],
    manifest_hash_before: str,
    manifest_hash_after: str,
    model_version_id: str | None,
    error: str | None,
) -> dict[str, Any]:
    succeeded = returncode == 0 and bool(artifact_validation.get("ok"))
    return {
        "phase": "phase-4-ace-real-training-smoke",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "phase3_report_path": phase3.get("report_path"),
        "frozen_dataset_id": run.dataset_slice_id,
        "frozen_manifest_hash": phase3.get("frozen_manifest_hash"),
        "frozen_manifest_file_hash_before": manifest_hash_before,
        "frozen_manifest_file_hash_after": manifest_hash_after,
        "frozen_manifest_immutable": manifest_hash_before == manifest_hash_after,
        "source_media_ids": phase3.get("source_media_ids", []),
        "source_file_paths": phase3.get("source_file_paths", []),
        "workspace_path": str(Path(phase3["workspace_path"])),
        "base_model_name": run.base_model_name,
        "training_mode": run.training_mode,
        "artifact_type": run.artifact_type,
        "training_run": {
            "id": run.id,
            "status": run.status.value,
            "dataset_slice_id": run.dataset_slice_id,
            "artifact_path": run.artifact_path,
            "model_version_id": model_version_id,
            "error": run.error or error,
        },
        "command": command,
        "stdout_log_path": str(stdout_path),
        "stderr_log_path": str(stderr_path),
        "train_log_path": str(train_log_path),
        "start_time": start_time,
        "end_time": end_time,
        "returncode": returncode,
        "runtime_profile": runtime_profile,
        "artifact_validation": artifact_validation,
        "produced_files": produced_files,
        "model_version_created": model_version_id is not None,
        "success": succeeded and manifest_hash_before == manifest_hash_after and model_version_id is not None,
        "error": error,
    }


def _smallest_smoke_config(data_dir: Path, manifest_hash: str) -> dict[str, Any]:
    config = resolve_training_preset("calibration")
    config.update(
        {
            "evidence_phase": "phase-4-ace-real-training-smoke",
            "dataset_manifest_hash": manifest_hash,
            "runtime_profile": _load_runtime_profile(data_dir),
            "real_ace_training": True,
            "epochs": 1,
            "steps": 1,
            "rank": 4,
            "learning_rate": 1e-4,
            "base_model_name": BASE_MODEL_NAME,
            "training_mode": TRAINING_MODE,
            "artifact_type": ARTIFACT_TYPE,
        }
    )
    return config


def _build_runner_command(
    *,
    ace_python: Path,
    package_path: Path,
    config_path: Path,
    run_dir: Path,
    train_log_path: Path,
    checkpoint_root: Path,
    device: str,
    ace_step_dir: Path,
) -> list[str]:
    return [
        str(ace_python),
        str((ROOT / "scripts" / "ace_train_runner.py").resolve()),
        "--package",
        str(package_path),
        "--config",
        str(config_path),
        "--output-dir",
        str(run_dir),
        "--log",
        str(train_log_path),
        "--checkpoint-dir",
        str(checkpoint_root),
        "--device",
        device,
        "--ace-step-dir",
        str(ace_step_dir),
    ]


def _create_training_run(
    *,
    dataset_id: str,
    manifest_hash: str,
    data_dir: Path,
    run_store: TrainingRunStore,
) -> TrainingRun:
    now = datetime.now(timezone.utc)
    config = _smallest_smoke_config(data_dir, manifest_hash)
    run = TrainingRun(
        name="Bell fixture ACE real smoke",
        dataset_slice_id=dataset_id,
        backend="ace-step-real-smoke",
        base_model_id=BASE_MODEL_NAME,
        base_model_name=BASE_MODEL_NAME,
        training_mode=TRAINING_MODE,
        artifact_type=ARTIFACT_TYPE,
        config_preset="calibration",
        config=config,
        status=JobStatus.QUEUED,
        created_at=now,
        updated_at=now,
    )
    run_store.save(run)
    run_store.write_config(run.id, config)
    return run


def verify_ace_real_training_smoke(*, run_training: bool = False) -> dict[str, Any]:
    if not real_training_smoke_enabled(run_training):
        raise RuntimeError(f"Real ACE training smoke is gated. Set {GATE_ENV}=1 or pass --run to execute.")

    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()

    phase3 = verify_ace_training_contract_flow()
    dataset_id = str(phase3["frozen_dataset_id"])
    slice_store = SliceStore(settings.slices_dir)
    dataset = slice_store.get(dataset_id)
    if dataset is None or dataset.status != DatasetSliceStatus.READY:
        raise RuntimeError(f"Frozen Bell dataset is not READY: {dataset_id}")

    manifest_path = settings.slices_dir / dataset.id / "manifest.json"
    manifest_text_before = manifest_path.read_text(encoding="utf-8")
    manifest_file_hash_before = _sha256(manifest_path)
    manifest = json.loads(manifest_text_before)
    manifest_hash = str(manifest.get("manifest_hash") or "")
    if not manifest_hash:
        raise RuntimeError("Frozen Bell dataset manifest has no manifest_hash")

    services = _services(settings)
    slice_service: SliceService = services["slice_service"]
    package_path = slice_service.build_package_path(dataset.id)

    run_store = TrainingRunStore(settings.training_runs_dir)
    run = _create_training_run(
        dataset_id=dataset.id,
        manifest_hash=manifest_hash,
        data_dir=settings.data_dir,
        run_store=run_store,
    )
    run_dir = run_store.run_dir(run.id)
    train_log_path = run_store.log_path(run.id)
    stdout_path = run_store.logs_dir(run.id) / "smoke.stdout.log"
    stderr_path = run_store.logs_dir(run.id) / "smoke.stderr.log"
    ace_step_dir = _absolute_no_symlink(settings.ace_step_dir) if settings.ace_step_dir else None
    if ace_step_dir is None:
        raise RuntimeError("ACE_STEP_DIR is required for real ACE training smoke")
    ace_python = _absolute_no_symlink(settings.ace_python)
    checkpoint_root = (
        _absolute_no_symlink(settings.ace_train_checkpoint_dir)
        if settings.ace_train_checkpoint_dir is not None
        else _absolute_no_symlink(settings.ace_model_dir)
    )
    command = _build_runner_command(
        ace_python=ace_python,
        package_path=package_path,
        config_path=run_dir / "config.json",
        run_dir=run_dir,
        train_log_path=train_log_path,
        checkpoint_root=checkpoint_root,
        device=settings.ace_device,
        ace_step_dir=ace_step_dir,
    )

    now = datetime.now(timezone.utc)
    run = run.model_copy(update={"status": JobStatus.RUNNING, "started_at": now, "updated_at": now})
    run_store.save(run)
    run_store.append_log(run.id, "phase 4 evidence: real ACE training smoke started")

    start_time = datetime.now(timezone.utc).isoformat()
    returncode: int | None = None
    error: str | None = None
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            result = subprocess.run(
                command,
                cwd=str(ROOT),
                stdout=stdout,
                stderr=stderr,
                check=False,
                timeout=settings.ace_train_timeout_seconds,
            )
        returncode = result.returncode
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        error = f"ACE real training smoke timed out after {exc.timeout} seconds"
    end_time = datetime.now(timezone.utc).isoformat()

    final_dir = run_adapter_final_dir(run_dir)
    artifact_validation = validate_adapter_artifact(final_dir)
    produced_files = collect_produced_files(run_dir)
    artifact_rel = _relative_to_data(final_dir, settings.data_dir)
    manifest_file_hash_after = _sha256(manifest_path)
    frozen_manifest_immutable = manifest_file_hash_before == manifest_file_hash_after
    model_version_id: str | None = None

    if returncode == 0 and artifact_validation["ok"] and frozen_manifest_immutable:
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
        style_service = StyleVersionService(StyleVersionStore(settings.style_versions_dir))
        model_version = style_service.create_from_run(run, dataset.name, status=StyleVersionStatus.CANDIDATE)
        model_version_id = model_version.id
        run = run.model_copy(update={"style_version_id": model_version_id, "updated_at": datetime.now(timezone.utc)})
        run_store.save(run)
        run_store.append_log(run.id, f"phase 4 evidence: registered real smoke model version {model_version_id}")
    else:
        finished_at = datetime.now(timezone.utc)
        if error is None:
            error = (
                "ACE real training smoke failed: "
                f"returncode={returncode}, artifact_ok={artifact_validation['ok']}, "
                f"frozen_manifest_immutable={frozen_manifest_immutable}"
            )
        run = run.model_copy(
            update={
                "status": JobStatus.FAILED,
                "finished_at": finished_at,
                "updated_at": finished_at,
                "error": error,
            }
        )
        run_store.save(run)
        run_store.append_log(run.id, error)

    runtime_profile = _load_runtime_profile(settings.data_dir)
    report = build_report_payload(
        phase3=phase3,
        run=run,
        command=command,
        stdout_path=stdout_path,
        stderr_path=stderr_path,
        train_log_path=train_log_path,
        start_time=start_time,
        end_time=end_time,
        returncode=returncode,
        runtime_profile=runtime_profile,
        artifact_validation=artifact_validation,
        produced_files=produced_files,
        manifest_hash_before=manifest_file_hash_before,
        manifest_hash_after=manifest_file_hash_after,
        model_version_id=model_version_id,
        error=error,
    )
    report_dir = settings.data_dir / "experiments" / "ace-real-training-smoke"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    if not report["success"]:
        raise RuntimeError(f"ACE real training smoke failed; report written to {report_path}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the explicitly gated Phase 4 real ACE training smoke test")
    parser.add_argument("--run", action="store_true", help=f"Run real ACE training even without {GATE_ENV}=1")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not real_training_smoke_enabled(args.run):
        message = f"ACE real training smoke is gated. Set {GATE_ENV}=1 or pass --run to execute. No training was run."
        print(message)
        return 0

    report = verify_ace_real_training_smoke(run_training=args.run)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("ACE real training smoke: PASS")
        print(f"Frozen Bell dataset: {report['frozen_dataset_id']}")
        print(f"Training run: {report['training_run']['id']}")
        print(f"Model version: {report['training_run']['model_version_id']}")
        print(f"Artifact: {report['training_run']['artifact_path']}")
        print(f"Report: {report['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
