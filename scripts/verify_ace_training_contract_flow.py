#!/usr/bin/env python3
"""Verify Phase 3 ACE training workspace and command contract without training."""

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
from app.domain.enums import DatasetSliceStatus
from app.domain.models import JobStatus
from app.domain.training import TrainingRun
from app.domain.training_presets import resolve_training_preset
from app.services.category_service import CategoryService
from app.services.concept_service import ConceptService
from app.services.slice_package_service import SlicePackageService
from app.services.slice_service import SliceService
from app.storage.assignment_store import AssignmentStore
from app.storage.category_store import CategoryStore
from app.storage.concept_store import ConceptStore
from app.storage.local_media_store import LocalMediaStore
from app.storage.slice_store import SliceStore
from app.storage.training_run_store import TrainingRunStore
from app.training.ace_package_converter import unpack_studio_package, write_ace_dataset_json
from app.training.ace_train_commands import build_preprocess_command, build_train_command, run_ace_output_dir, run_tensors_dir
from scripts.verify_mock_training_lineage_flow import ARTIFACT_TYPE, BASE_MODEL_NAME, TRAINING_MODE, verify_mock_training_lineage_flow

OLD_WINDOWS_CACHE = "/mnt/c/Users/Administrator/.cache/huggingface/ace-step-checkpoints"


def _absolute_no_symlink(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded
    return (ROOT / expanded).absolute()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _services(settings):
    media_store = LocalMediaStore(settings.media_dir)
    assignment_store = AssignmentStore(settings.assignments_dir)
    category_service = CategoryService(CategoryStore(settings.categories_dir))
    concept_service = ConceptService(ConceptStore(settings.concepts_dir), category_service)
    slice_store = SliceStore(settings.slices_dir)
    package_service = SlicePackageService(slice_store, media_store, assignment_store, category_service, settings)
    slice_service = SliceService(
        slice_store,
        media_store,
        assignment_store,
        category_service,
        concept_service,
        package_service,
    )
    return {
        "slice_store": slice_store,
        "slice_service": slice_service,
        "package_service": package_service,
    }


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _track_duration(package_root: Path, sample_id: str) -> float:
    annotation = _read_json(package_root / "tracks" / sample_id / "annotation.json")
    music = annotation.get("music") if isinstance(annotation.get("music"), dict) else {}
    return float(music.get("duration_seconds") or 0)


def _validate_report_item(results: dict[str, bool], key: str, value: bool) -> None:
    results[key] = bool(value)


def verify_ace_training_contract_flow() -> dict:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()

    phase2 = verify_mock_training_lineage_flow()
    dataset_id = phase2["dataset"]["slice_id"]
    services = _services(settings)
    dataset = services["slice_store"].get(dataset_id)
    if dataset is None:
        raise RuntimeError(f"Frozen Bell dataset not found: {dataset_id}")
    if dataset.status != DatasetSliceStatus.READY:
        raise RuntimeError(f"Bell dataset is not READY: {dataset.status}")

    frozen_manifest_path = settings.slices_dir / dataset.id / "manifest.json"
    frozen_manifest_before_text = frozen_manifest_path.read_text(encoding="utf-8")
    frozen_manifest_before_file_hash = _sha256(frozen_manifest_path)
    frozen_manifest = _read_json(frozen_manifest_path)
    frozen_manifest_hash = str(frozen_manifest.get("manifest_hash") or "")
    if not frozen_manifest_hash:
        raise RuntimeError("Frozen Bell dataset manifest has no manifest_hash")

    config = resolve_training_preset("calibration")
    config.update(
        {
            "evidence_phase": "phase-3-ace-training-contract",
            "dataset_manifest_hash": frozen_manifest_hash,
            "real_ace_training": False,
            "preprocess_executed": False,
        }
    )
    now = datetime.now(timezone.utc)
    run = TrainingRun(
        name="Bell fixture ACE contract evidence",
        dataset_slice_id=dataset.id,
        backend="ace-step-contract",
        base_model_id=BASE_MODEL_NAME,
        base_model_name=BASE_MODEL_NAME,
        training_mode=TRAINING_MODE,
        artifact_type=ARTIFACT_TYPE,
        config_preset="calibration",
        config=config,
        status=JobStatus.SUCCEEDED,
        started_at=now,
        finished_at=now,
        created_at=now,
        updated_at=now,
    )
    run_store = TrainingRunStore(settings.training_runs_dir)
    run_store.save(run)
    run_store.write_config(run.id, config)
    run_store.append_log(run.id, "phase 3 evidence: ACE workspace/command contract started")

    run_dir = run_store.run_dir(run.id)
    workspace_dir = run_dir / "workspace"
    package_path = services["slice_service"].build_package_path(dataset.id)
    package_root = unpack_studio_package(package_path, workspace_dir)
    ace_dataset_path = write_ace_dataset_json(
        package_root,
        config={
            "name": dataset.name,
            "custom_tag": "Bell",
            "language": "en",
        },
    )
    ace_dataset = _read_json(ace_dataset_path)

    ace_step_dir = _absolute_no_symlink(settings.ace_step_dir) if settings.ace_step_dir else None
    ace_python = _absolute_no_symlink(settings.ace_python)
    checkpoint_root = (
        _absolute_no_symlink(settings.ace_train_checkpoint_dir)
        if settings.ace_train_checkpoint_dir is not None
        else _absolute_no_symlink(settings.ace_model_dir)
    )
    train_script = ace_step_dir / "train.py" if ace_step_dir else Path("")
    tensor_dir = run_tensors_dir(run_dir)
    ace_output_dir = run_ace_output_dir(run_dir)
    planned_artifact_dir = ace_output_dir / "final"
    tensor_dir.mkdir(parents=True, exist_ok=True)
    ace_output_dir.mkdir(parents=True, exist_ok=True)

    preprocess_command = build_preprocess_command(
        ace_python=ace_python,
        checkpoint_dir=checkpoint_root,
        audio_dir=package_root,
        dataset_json=ace_dataset_path,
        tensor_output=tensor_dir,
        device=settings.ace_device,
    )
    train_command = build_train_command(
        ace_python=ace_python,
        train_script=train_script,
        checkpoint_dir=checkpoint_root,
        dataset_dir=tensor_dir,
        output_dir=ace_output_dir,
        epochs=int(config.get("epochs", 1)),
        rank=int(config.get("rank", 8)),
        learning_rate=float(config.get("learning_rate", 1e-4)),
        device=settings.ace_device,
    )
    next_real_training_command = [
        str(ace_python),
        str((ROOT / "scripts" / "ace_train_runner.py").resolve()),
        "--package",
        str(package_path),
        "--config",
        str(run_dir / "config.json"),
        "--output-dir",
        str(run_dir),
        "--log",
        str(run_store.log_path(run.id)),
        "--checkpoint-dir",
        str(checkpoint_root),
        "--device",
        settings.ace_device,
        "--ace-step-dir",
        str(ace_step_dir) if ace_step_dir else "",
    ]

    samples = ace_dataset.get("samples", [])
    sample_audio_paths = [package_root / str(sample["audio_path"]).removeprefix("./") for sample in samples]
    sample_label_paths = [package_root / "tracks" / str(sample["id"]) / "labels.json" for sample in samples]
    sample_durations = [_track_duration(package_root, str(sample["id"])) for sample in samples]
    frozen_category_ids = {
        category["category_id"]
        for track in frozen_manifest.get("tracks", [])
        for category in track.get("categories", [])
    }
    workspace_category_ids = {
        category["category_id"]
        for labels_path in sample_label_paths
        for category in _read_json(labels_path).get("categories", [])
    }
    command_blob = "\n".join([" ".join(preprocess_command), " ".join(train_command), " ".join(next_real_training_command)])

    validations: dict[str, bool] = {}
    _validate_report_item(validations, "dataset_files_exist", bool(sample_audio_paths) and all(path.is_file() for path in sample_audio_paths))
    _validate_report_item(validations, "manifest_exists", ace_dataset_path.is_file())
    _validate_report_item(validations, "manifest_references_real_files", all(path.is_file() for path in sample_audio_paths))
    _validate_report_item(
        validations,
        "total_duration_matches_frozen_manifest",
        round(sum(sample_durations), 3) == round(float(frozen_manifest.get("total_duration_seconds") or 0), 3),
    )
    _validate_report_item(validations, "category_lineage_preserved", frozen_category_ids.issubset(workspace_category_ids))
    _validate_report_item(validations, "checkpoint_root_exists", checkpoint_root.is_dir())
    _validate_report_item(validations, "turbo_checkpoint_exists", (checkpoint_root / "acestep-v15-turbo").is_dir())
    _validate_report_item(validations, "ace_python_exists", ace_python.is_file())
    _validate_report_item(validations, "output_artifact_directory_planned", planned_artifact_dir.parent.is_dir())
    _validate_report_item(
        validations,
        "command_uses_external_ace_python",
        preprocess_command[0] == str(ace_python)
        and train_command[0] == str(ace_python)
        and str(ace_python).endswith("/ACE-Step-1.5/.venv/bin/python"),
    )
    _validate_report_item(validations, "command_has_no_base_model_version", "base_model_version" not in command_blob)
    _validate_report_item(validations, "command_has_no_old_windows_hf_cache", OLD_WINDOWS_CACHE not in command_blob)
    _validate_report_item(validations, "frozen_manifest_immutable", frozen_manifest_path.read_text(encoding="utf-8") == frozen_manifest_before_text)
    _validate_report_item(validations, "full_training_not_run", not planned_artifact_dir.exists())

    success = all(validations.values())
    if not success:
        failed = [key for key, value in validations.items() if not value]
        raise RuntimeError(f"ACE training contract validation failed: {failed}")

    command_manifest = {
        "dry_run_contract_only": True,
        "preprocess_executed": False,
        "preprocess_command": preprocess_command,
        "train_command": train_command,
        "next_real_training_command": next_real_training_command,
        "workspace": str(workspace_dir),
        "package_root": str(package_root),
        "ace_dataset_path": str(ace_dataset_path),
        "planned_artifact_dir": str(planned_artifact_dir),
        "rendered_at": datetime.now(timezone.utc).isoformat(),
    }
    command_manifest_path = run_dir / "ace_training_contract_command.json"
    command_manifest_path.write_text(json.dumps(command_manifest, indent=2), encoding="utf-8")
    run_store.append_log(run.id, "phase 3 evidence: rendered ACE preprocess/train commands without execution")

    frozen_manifest_after_file_hash = _sha256(frozen_manifest_path)
    source_paths = [track.get("file_path") for track in frozen_manifest.get("tracks", [])]
    report = {
        "phase": "phase-3-ace-training-contract-flow",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "phase2_report_path": phase2.get("report_path"),
        "training_run_id": run.id,
        "frozen_dataset_id": dataset.id,
        "frozen_manifest_hash": frozen_manifest_hash,
        "frozen_manifest_file_hash_before": frozen_manifest_before_file_hash,
        "frozen_manifest_file_hash_after": frozen_manifest_after_file_hash,
        "source_media_ids": list(frozen_manifest.get("media_ids", [])),
        "source_file_paths": source_paths,
        "workspace_path": str(workspace_dir),
        "studio_package_path": str(package_path),
        "ace_manifest_path": str(ace_dataset_path),
        "command_manifest_path": str(command_manifest_path),
        "generated_command": {
            "preprocess": preprocess_command,
            "train": train_command,
        },
        "next_command_that_would_run_real_training": next_real_training_command,
        "base_model_name": BASE_MODEL_NAME,
        "training_mode": TRAINING_MODE,
        "artifact_type": ARTIFACT_TYPE,
        "checkpoint_root": str(checkpoint_root),
        "ace_step_dir": str(ace_step_dir) if ace_step_dir else "",
        "ace_python": str(ace_python),
        "planned_artifact_dir": str(planned_artifact_dir),
        "validation_results": validations,
        "preprocess_executed": False,
        "full_training_executed": False,
        "success": success,
    }
    report_dir = settings.data_dir / "experiments" / "ace-training-contract-flow"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 3 ACE training workspace/command contract")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = verify_ace_training_contract_flow()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("ACE training contract flow: PASS")
        print(f"Frozen Bell dataset: {report['frozen_dataset_id']} manifest={report['frozen_manifest_hash']}")
        print(f"Training run: {report['training_run_id']}")
        print(f"Workspace: {report['workspace_path']}")
        print(f"ACE dataset manifest: {report['ace_manifest_path']}")
        print(f"Checkpoint root: {report['checkpoint_root']}")
        print(f"Next real command: {' '.join(report['next_command_that_would_run_real_training'])}")
        print(f"Report: {report['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
