#!/usr/bin/env python3
"""Verify Synthetic Dark Bell v1 LoRA training and base-vs-LoRA comparison flow.

Pipeline
--------
1.  Ensure Synthetic Dark Bell v1 is generated and frozen as a READY dataset.
2.  Create a TrainingRun (base_model=acestep-v15-turbo, mode=lora_finetune,
    artifact_type=lora) backed by the frozen dataset.
3.  Run ACE LoRA training via scripts/ace_train_runner.py.
4.  Normalize ACE/PEFT adapter outputs into Studio LoRA names:
      adapter_model.safetensors  →  lora.safetensors
      adapter_config.json        →  lora_config.json
    Original PEFT files are kept; Studio names are the authoritative surface.
5.  Write lora_manifest.json referencing Studio names.
6.  Create a Model Version (StyleVersion) only when lora.safetensors is nonzero.
7.  Preserve lineage: Model Version → TrainingRun → frozen Synthetic Dark Bell dataset.
8.  Plan and optionally execute 3 prompts × 3 seeds of base-vs-LoRA comparison.
9.  Validate any produced WAVs with ffprobe; collect duration, size, RMS, and peak.
10. Write a timestamped report under data/experiments/synthetic-dark-bell-lora/<ts>/.

DISCLAIMER
----------
Results from this comparison prove influence/comparison only.
They do NOT guarantee automatic quality improvement.

GATE: set SYNTH_LORA_TRAINING_FLOW=1 to allow real ACE training.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import struct
import subprocess
import sys
import wave as _wave
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
from app.domain.models import JobStatus, GenerationRequest
from app.domain.training import TrainingRun
from app.domain.training_presets import resolve_training_preset
from app.domain.training_status import is_real_ace_backend
from app.generators.ace_step.command_builder import AceCommandBuilder
from app.services.style_version_service import StyleVersionService
from app.storage.slice_store import SliceStore
from app.storage.style_version_store import StyleVersionStore
from app.storage.training_run_store import TrainingRunStore
from app.training.ace_subprocess_env import ace_training_env
from app.training.ace_train_commands import (
    LORA_CONFIG_NAME,
    LORA_MANIFEST_NAME,
    LORA_WEIGHTS_NAME,
    normalize_lora_artifact,
    resolve_lora_files,
    run_adapter_final_dir,
    run_artifacts_dir,
)

from scripts.verify_synthetic_instrument_dataset_flow import (
    PACK_NAME,
    verify_synthetic_instrument_dataset_flow,
)

# ── Constants ──────────────────────────────────────────────────────────────────

GATE_ENV = "SYNTH_LORA_TRAINING_FLOW"

BASE_MODEL_ID   = "acestep-v15-turbo"
BASE_MODEL_NAME = "ACE-Step v1.5 Turbo"
TRAINING_MODE   = "lora_finetune"
ARTIFACT_TYPE   = "lora"

COMPARISON_PROMPTS = [
    "sparse dark glass bell tones with long metallic shimmer",
    "minimal ambient music with distant synthetic bell pulses",
    "cinematic dark bell texture with metallic decay and quiet space",
]
COMPARISON_SEEDS = [42, 1337, 8675309]

COMPARISON_DURATION_SECONDS = 15   # short clips for comparison
COMPARISON_DISCLAIMER = (
    "These outputs demonstrate LoRA influence on model behavior relative to the base model. "
    "Presence of difference is expected; this comparison does NOT prove automatic quality improvement."
)


# ── Gate helpers ───────────────────────────────────────────────────────────────

def is_flow_enabled(flag: bool = False) -> bool:
    """Return True only when the real LoRA training gate is open."""
    return flag or os.environ.get(GATE_ENV, "").strip() == "1"


# ── Lineage validation ─────────────────────────────────────────────────────────

def validate_lineage(run: TrainingRun, model_version, dataset) -> tuple[bool, list[str]]:
    """Verify the Model Version → TrainingRun → Dataset chain.

    Returns (ok, list_of_failures).
    """
    failures: list[str] = []
    if model_version.training_run_id != run.id:
        failures.append(f"model_version.training_run_id {model_version.training_run_id!r} != run.id {run.id!r}")
    if run.dataset_slice_id != dataset.id:
        failures.append(f"run.dataset_slice_id {run.dataset_slice_id!r} != dataset.id {dataset.id!r}")
    if model_version.dataset_slice_id != dataset.id:
        failures.append(f"model_version.dataset_slice_id {model_version.dataset_slice_id!r} != dataset.id {dataset.id!r}")
    if model_version.base_model_name != BASE_MODEL_NAME:
        failures.append(f"model_version.base_model_name {model_version.base_model_name!r} != {BASE_MODEL_NAME!r}")
    if model_version.training_mode != TRAINING_MODE:
        failures.append(f"model_version.training_mode {model_version.training_mode!r} != {TRAINING_MODE!r}")
    if model_version.artifact_type != ARTIFACT_TYPE:
        failures.append(f"model_version.artifact_type {model_version.artifact_type!r} != {ARTIFACT_TYPE!r}")
    return (len(failures) == 0), failures


def validate_lora_naming(final_dir: Path) -> dict[str, Any]:
    """Verify Studio LoRA file names exist and have nonzero size."""
    results: dict[str, Any] = {}
    for name in (LORA_WEIGHTS_NAME, LORA_CONFIG_NAME):
        path = final_dir / name
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
        results[name] = {"path": str(path), "exists": exists, "size_bytes": size, "nonzero": size > 0}
    manifest_path = final_dir.parent.parent / LORA_MANIFEST_NAME   # artifacts_dir
    results[LORA_MANIFEST_NAME] = {
        "path": str(manifest_path),
        "exists": manifest_path.is_file(),
        "size_bytes": manifest_path.stat().st_size if manifest_path.is_file() else 0,
    }
    all_ok = all(v.get("exists") and v.get("nonzero", True) for v in results.values())
    return {"files": results, "ok": all_ok, "final_dir": str(final_dir)}


# ── Comparison pair planning ───────────────────────────────────────────────────

def plan_comparison_pairs(
    experiment_dir: Path,
    lora_final_dir: Path | None,
    *,
    lora_available: bool = False,
) -> list[dict[str, Any]]:
    """Return the 9 base-vs-LoRA comparison pair descriptors (pure function).

    No generation is attempted here.  Each entry has:
      pair_id, prompt, seed, base_output, lora_output, lora_path, generation_status
    """
    lora_path_str = str(lora_final_dir) if lora_final_dir and lora_available else None
    pairs: list[dict[str, Any]] = []
    for pi, prompt in enumerate(COMPARISON_PROMPTS):
        for si, seed in enumerate(COMPARISON_SEEDS):
            pair_id = f"pair_p{pi}_s{si}"
            pairs.append({
                "pair_id":           pair_id,
                "prompt_index":      pi,
                "seed_index":        si,
                "prompt":            prompt,
                "seed":              seed,
                "duration_seconds":  COMPARISON_DURATION_SECONDS,
                "base_output":       str(experiment_dir / f"{pair_id}_base.wav"),
                "lora_output":       str(experiment_dir / f"{pair_id}_lora.wav"),
                "lora_path":         lora_path_str,
                "generation_status": "planned",
                "base_stats":        None,
                "lora_stats":        None,
            })
    return pairs


# ── Pair success checks ────────────────────────────────────────────────────────

def _pair_succeeded(pair: dict[str, Any]) -> bool:
    """Return True only when both base WAV (and LoRA WAV when expected) validated."""
    base_stats = pair.get("base_stats")
    if not (base_stats and base_stats.get("valid")):
        return False
    if pair.get("lora_path"):
        lora_stats = pair.get("lora_stats")
        if not (lora_stats and lora_stats.get("valid")):
            return False
    return True


def _all_pairs_succeeded(pairs: list[dict[str, Any]]) -> bool:
    return all(_pair_succeeded(p) for p in pairs)


# ── WAV / ffprobe validation ───────────────────────────────────────────────────

def _ffprobe_wav(path: Path) -> dict[str, Any] | None:
    """Return ffprobe format/stream metadata for the file, or None on failure."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=10)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {}
        )
        return {
            "duration_seconds": round(float(fmt.get("duration") or stream.get("duration") or 0), 3),
            "size_bytes": int(fmt.get("size") or 0),
            "sample_rate": int(stream.get("sample_rate") or 0),
            "channels": int(stream.get("channels") or 0),
            "codec": stream.get("codec_name", ""),
        }
    except Exception:
        return None


def _wav_rms_peak(path: Path) -> dict[str, float]:
    """Compute RMS and peak from raw PCM samples (stdlib only)."""
    try:
        with _wave.open(str(path), "rb") as wf:
            n_frames = wf.getnframes()
            n_channels = wf.getnchannels()
            raw = wf.readframes(n_frames)
        n_samples = len(raw) // 2
        values = struct.unpack(f"<{n_samples}h", raw)
        peak = max(abs(v) for v in values) / 32767.0 if values else 0.0
        rms_raw = math.sqrt(sum(v * v for v in values) / len(values)) if values else 0.0
        rms = rms_raw / 32767.0
        return {"rms": round(rms, 6), "peak": round(peak, 6)}
    except Exception:
        return {"rms": 0.0, "peak": 0.0}


def validate_wav_file(path: Path) -> dict[str, Any]:
    """Full WAV validation: ffprobe format check + RMS/peak stats."""
    exists = path.is_file()
    if not exists:
        return {"path": str(path), "exists": False, "valid": False, "ffprobe": None, "rms": 0.0, "peak": 0.0}
    ffprobe = _ffprobe_wav(path)
    amp = _wav_rms_peak(path)
    valid = ffprobe is not None and ffprobe.get("duration_seconds", 0) > 0
    return {
        "path": str(path),
        "exists": True,
        "valid": valid,
        "ffprobe": ffprobe,
        **amp,
    }


# ── Generation (gated, best-effort) ───────────────────────────────────────────

def _ace_command_configured(settings) -> bool:
    return bool(settings.ace_command_template.strip()) and settings.ace_enabled


def _attempt_generation(
    pair: dict[str, Any],
    settings,
    ace_step_dir: Path,
    *,
    use_lora: bool,
) -> dict[str, Any]:
    """Try to generate one WAV via ACE.  Returns pair dict with updated status."""
    result = dict(pair)
    output_path = Path(pair["lora_output"] if use_lora else pair["base_output"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        builder = AceCommandBuilder(settings)
        req = GenerationRequest(
            title=f"{'LoRA' if use_lora else 'Base'} {pair['pair_id']}",
            prompt=pair["prompt"],
            mode="instrumental",
            duration_seconds=pair["duration_seconds"],
            seed=pair["seed"],
            lora_path=pair["lora_path"] if use_lora else None,
            lora_scale=1.0,
        )
        command = builder.build(req, output_path)
        env = ace_training_env(ace_step_dir=ace_step_dir)
        proc = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=120, env=env
        )
        if proc.returncode == 0 and output_path.is_file():
            stats = validate_wav_file(output_path)
            key = "lora_stats" if use_lora else "base_stats"
            result[key] = stats
            result["generation_status"] = "succeeded"
        else:
            result["generation_status"] = "failed"
            result["generation_error"] = (proc.stderr or proc.stdout or "")[:400]
    except subprocess.TimeoutExpired:
        result["generation_status"] = "timeout"
    except Exception as exc:
        result["generation_status"] = "error"
        result["generation_error"] = str(exc)[:400]
    return result


def run_comparison(
    pairs: list[dict[str, Any]],
    settings,
    lora_final_dir: Path | None,
    *,
    mandatory: bool = False,
) -> list[dict[str, Any]]:
    """Attempt generation for each pair.

    When mandatory=True, raises RuntimeError if ACE is not configured or
    model paths are missing, rather than degrading silently.
    """
    if not _ace_command_configured(settings):
        if mandatory:
            raise RuntimeError(
                "Mandatory comparison requires ACE to be configured "
                "(ACE_ENABLED=true and ace_command_template set). "
                "Pass --train-only or --allow-planned-comparison to skip."
            )
        return [dict(p, generation_status="skipped_ace_not_configured") for p in pairs]

    ace_step_dir = settings.ace_step_dir
    if ace_step_dir is None or not ace_step_dir.is_dir():
        if mandatory:
            raise RuntimeError(
                "Mandatory comparison requires ACE_STEP_DIR to be a valid directory. "
                "Pass --train-only or --allow-planned-comparison to skip."
            )
        return [dict(p, generation_status="skipped_ace_step_dir_missing") for p in pairs]
    ace_step_dir = ace_step_dir.expanduser().resolve()

    updated = []
    for pair in pairs:
        # Base generation (no LoRA)
        pair = _attempt_generation(pair, settings, ace_step_dir, use_lora=False)
        # LoRA generation (only if LoRA path is set and files exist)
        if pair.get("lora_path") and lora_final_dir and (lora_final_dir / LORA_WEIGHTS_NAME).is_file():
            pair = _attempt_generation(pair, settings, ace_step_dir, use_lora=True)
        else:
            pair = dict(pair, lora_stats=None,
                        generation_status=pair.get("generation_status", "skipped_no_lora"))
        updated.append(pair)
    return updated


# ── Training run management ────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_training_config(manifest_hash: str, settings) -> dict[str, Any]:
    config = resolve_training_preset("calibration")
    config.update({
        "evidence_phase": "synthetic-dark-bell-v1-lora-training",
        "dataset_manifest_hash": manifest_hash,
        "base_model_name": BASE_MODEL_NAME,
        "training_mode": TRAINING_MODE,
        "artifact_type": ARTIFACT_TYPE,
        "real_ace_training": True,
        "epochs": 1,
        "steps": 50,    # minimal smoke for this evidence phase
        "rank": 4,
        "learning_rate": 1e-4,
    })
    return config


def _create_training_run(
    *,
    dataset_id: str,
    manifest_hash: str,
    settings,
    run_store: TrainingRunStore,
) -> TrainingRun:
    now = datetime.now(timezone.utc)
    config = _build_training_config(manifest_hash, settings)
    run = TrainingRun(
        name="Synthetic Dark Bell v1 LoRA",
        dataset_slice_id=dataset_id,
        backend="ace-step-real",
        base_model_id=BASE_MODEL_ID,
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
    run_store.append_log(run.id, "synthetic-dark-bell-v1: LoRA training queued")
    return run


def _absolute(path: Path | None) -> Path | None:
    if path is None:
        return None
    return path.expanduser().resolve()


def _runner_command(
    *,
    package_path: Path,
    run_dir: Path,
    train_log_path: Path,
    checkpoint_dir: Path,
    device: str,
    ace_step_dir: Path,
    ace_python: Path,
) -> list[str]:
    return [
        str(ace_python),
        str((ROOT / "scripts" / "ace_train_runner.py").resolve()),
        "--package", str(package_path),
        "--config", str(run_dir / "config.json"),
        "--output-dir", str(run_dir),
        "--log", str(train_log_path),
        "--checkpoint-dir", str(checkpoint_dir),
        "--device", device,
        "--ace-step-dir", str(ace_step_dir),
    ]


def _write_lora_manifest(
    artifacts_dir: Path,
    final_dir: Path,
    *,
    run_id: str,
    dataset_id: str,
    manifest_hash: str,
) -> Path:
    lora_weights = final_dir / LORA_WEIGHTS_NAME
    lora_config = final_dir / LORA_CONFIG_NAME
    payload = {
        "artifact_type": "LoRA",
        "artifact_path": "ace_output/final",
        "lora_path": str(final_dir.resolve()),
        "load_path": str(final_dir.resolve()),
        "required_files": {
            LORA_WEIGHTS_NAME: str(lora_weights.resolve()),
            LORA_CONFIG_NAME: str(lora_config.resolve()),
        },
        "base_model_name": BASE_MODEL_NAME,
        "training_mode": TRAINING_MODE,
        "artifact_type_field": ARTIFACT_TYPE,
        "training_run_id": run_id,
        "dataset_slice_id": dataset_id,
        "dataset_manifest_hash": manifest_hash,
        "model_variant": "turbo",
        "disclaimer": COMPARISON_DISCLAIMER,
        "written_at": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = artifacts_dir / LORA_MANIFEST_NAME
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # legacy alias kept for other tooling
    legacy = artifacts_dir / "artifact_manifest.json"
    legacy.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


# ── Main flow ──────────────────────────────────────────────────────────────────

def verify_synthetic_lora_training_flow(
    *,
    run_training: bool = False,
    pack_dir: Path | None = None,
    clip_count: int = 80,
    min_dur: float = 8.0,
    max_dur: float = 15.0,
    mandatory_comparison: bool = True,
    train_only: bool = False,
) -> dict[str, Any]:
    if not is_flow_enabled(run_training):
        raise RuntimeError(
            f"Synthetic Dark Bell LoRA training flow is gated. "
            f"Set {GATE_ENV}=1 or pass --run to execute."
        )

    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()

    # ── Step 1: ensure frozen dataset ─────────────────────────────────────────
    print("Step 1: ensuring Synthetic Dark Bell v1 frozen dataset…")
    dataset_report = verify_synthetic_instrument_dataset_flow(
        pack_dir=pack_dir,
        clip_count=clip_count,
        min_dur=min_dur,
        max_dur=max_dur,
    )
    dataset_id = dataset_report["frozen_dataset"]["slice_id"]
    slice_store = SliceStore(settings.slices_dir)
    dataset = slice_store.get(dataset_id)
    if dataset is None or dataset.status != DatasetSliceStatus.READY:
        raise RuntimeError(f"Dark Bell dataset is not READY: {dataset_id}")

    manifest_path = settings.slices_dir / dataset.id / "manifest.json"
    manifest_text_before = manifest_path.read_text(encoding="utf-8")
    manifest_file_hash_before = _sha256(manifest_path)
    manifest = json.loads(manifest_text_before)
    manifest_hash = str(manifest.get("manifest_hash") or "")
    if not manifest_hash:
        raise RuntimeError("Dark Bell dataset manifest has no manifest_hash")

    # ── Step 2: build training package path ───────────────────────────────────
    print("Step 2: building training package…")
    from app.services.slice_service import SliceService
    from app.services.category_service import CategoryService
    from app.services.concept_service import ConceptService
    from app.services.slice_package_service import SlicePackageService
    from app.storage.category_store import CategoryStore
    from app.storage.concept_store import ConceptStore
    from app.storage.local_media_store import LocalMediaStore
    from app.storage.assignment_store import AssignmentStore

    media_store = LocalMediaStore(settings.media_dir)
    assignment_store = AssignmentStore(settings.assignments_dir)
    category_service = CategoryService(CategoryStore(settings.categories_dir))
    concept_service = ConceptService(ConceptStore(settings.concepts_dir), category_service)
    slice_svc = SliceService(
        SliceStore(settings.slices_dir), media_store, assignment_store,
        category_service, concept_service,
        SlicePackageService(SliceStore(settings.slices_dir), media_store,
                            assignment_store, category_service, settings),
    )
    package_path = slice_svc.build_package_path(dataset.id)

    # ── Step 3: create TrainingRun ─────────────────────────────────────────────
    print("Step 3: creating TrainingRun…")
    run_store = TrainingRunStore(settings.training_runs_dir)
    run = _create_training_run(
        dataset_id=dataset.id,
        manifest_hash=manifest_hash,
        settings=settings,
        run_store=run_store,
    )
    run_dir = run_store.run_dir(run.id)
    train_log_path = run_store.log_path(run.id)
    artifacts_dir = run_store.artifacts_dir(run.id)

    # ── Step 4: resolve ACE paths ─────────────────────────────────────────────
    ace_step_dir = _absolute(settings.ace_step_dir)
    if ace_step_dir is None:
        raise RuntimeError("ACE_STEP_DIR is required for real ACE LoRA training")
    ace_python = _absolute(settings.ace_train_python) or (ace_step_dir / ".venv" / "bin" / "python")
    checkpoint_dir = _absolute(settings.ace_train_checkpoint_dir) or _absolute(settings.ace_model_dir)
    if checkpoint_dir is None:
        raise RuntimeError("ACE checkpoint dir required (ACE_TRAIN_CHECKPOINT_DIR or ACE_MODEL_DIR)")

    command = _runner_command(
        package_path=package_path,
        run_dir=run_dir,
        train_log_path=train_log_path,
        checkpoint_dir=checkpoint_dir,
        device=settings.ace_device,
        ace_step_dir=ace_step_dir,
        ace_python=ace_python,
    )

    # ── Step 5: run ACE training ───────────────────────────────────────────────
    print(f"Step 5: running ACE LoRA training ({run.id})…")
    stdout_log = run_store.logs_dir(run.id) / "synth_bell_lora.stdout.log"
    stderr_log = run_store.logs_dir(run.id) / "synth_bell_lora.stderr.log"
    now = datetime.now(timezone.utc)
    run = run.model_copy(update={"status": JobStatus.RUNNING, "started_at": now, "updated_at": now})
    run_store.save(run)
    run_store.append_log(run.id, "synthetic-dark-bell-v1: ACE training started")

    start_time = datetime.now(timezone.utc).isoformat()
    returncode: int | None = None
    error: str | None = None
    ace_env = ace_training_env(ace_step_dir=ace_step_dir)

    try:
        with stdout_log.open("w", encoding="utf-8") as so, stderr_log.open("w", encoding="utf-8") as se:
            result = subprocess.run(
                command, cwd=str(ROOT), env=ace_env,
                stdout=so, stderr=se, check=False,
                timeout=settings.ace_train_timeout_seconds,
            )
        returncode = result.returncode
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        error = f"ACE training timed out after {exc.timeout}s"
    end_time = datetime.now(timezone.utc).isoformat()

    # ── Step 6: normalize LoRA files to Studio names ───────────────────────────
    print("Step 6: normalizing LoRA artifacts to Studio names…")
    final_dir = run_adapter_final_dir(run_dir)
    normalize_lora_artifact(final_dir)
    lora_naming = validate_lora_naming(final_dir)
    artifact_ok = lora_naming["ok"]
    manifest_file_hash_after = _sha256(manifest_path)
    frozen_manifest_immutable = manifest_file_hash_before == manifest_file_hash_after

    # ── Step 7: write lora_manifest.json ──────────────────────────────────────
    lora_manifest_path: Path | None = None
    if artifact_ok:
        lora_manifest_path = _write_lora_manifest(
            artifacts_dir, final_dir,
            run_id=run.id, dataset_id=dataset.id, manifest_hash=manifest_hash,
        )

    # ── Step 8: create or skip Model Version ──────────────────────────────────
    print("Step 8: creating Model Version…")
    model_version_id: str | None = None
    lineage_ok: bool = False
    lineage_failures: list[str] = []

    if returncode == 0 and artifact_ok and frozen_manifest_immutable:
        finished_at = datetime.now(timezone.utc)
        artifact_rel = f"training_runs/{run.id}/artifacts/ace_output/final"
        run = run.model_copy(update={
            "status": JobStatus.SUCCEEDED,
            "artifact_path": artifact_rel,
            "finished_at": finished_at,
            "updated_at": finished_at,
            "error": None,
        })
        run_store.save(run)
        style_service = StyleVersionService(StyleVersionStore(settings.style_versions_dir))
        model_version = style_service.create_from_run(
            run, dataset.name, status=StyleVersionStatus.CANDIDATE
        )
        model_version_id = model_version.id
        run = run.model_copy(update={"style_version_id": model_version_id,
                                     "updated_at": datetime.now(timezone.utc)})
        run_store.save(run)
        run_store.append_log(run.id, f"synthetic-dark-bell-v1: Model Version registered {model_version_id}")
        lineage_ok, lineage_failures = validate_lineage(run, model_version, dataset)
    else:
        finished_at = datetime.now(timezone.utc)
        if error is None:
            error = (
                f"ACE LoRA training flow failed: returncode={returncode}, "
                f"artifact_ok={artifact_ok}, frozen_manifest_immutable={frozen_manifest_immutable}"
            )
        run = run.model_copy(update={
            "status": JobStatus.FAILED,
            "finished_at": finished_at,
            "updated_at": finished_at,
            "error": error,
        })
        run_store.save(run)
        run_store.append_log(run.id, error or "unknown failure")

    # ── Step 9: base-vs-LoRA comparison ───────────────────────────────────────
    print("Step 9: planning / running comparison…")
    experiment_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    experiment_dir = settings.data_dir / "experiments" / "synthetic-dark-bell-lora" / experiment_ts
    experiment_dir.mkdir(parents=True, exist_ok=True)

    lora_final_dir = final_dir if artifact_ok else None
    comparison_pairs = plan_comparison_pairs(
        experiment_dir, lora_final_dir, lora_available=artifact_ok
    )
    comparison_ok = True
    comparison_error: str | None = None

    if train_only:
        print("  Comparison skipped (--train-only).")
    elif artifact_ok:
        try:
            comparison_pairs = run_comparison(
                comparison_pairs, settings, lora_final_dir,
                mandatory=mandatory_comparison,
            )
        except RuntimeError as exc:
            comparison_error = str(exc)
            comparison_ok = False
            comparison_pairs = [dict(p, generation_status="failed") for p in comparison_pairs]

        if comparison_ok and mandatory_comparison:
            failed_pairs = [p for p in comparison_pairs if not _pair_succeeded(p)]
            if failed_pairs:
                comparison_ok = False
                statuses = sorted({p.get("generation_status", "unknown") for p in failed_pairs})
                comparison_error = (
                    f"{len(failed_pairs)}/9 comparison pairs did not produce valid WAVs "
                    f"(statuses: {statuses}). "
                    "Use --train-only or --allow-planned-comparison to suppress."
                )

    # ── Step 10: assemble report ───────────────────────────────────────────────
    produced_files = _collect_files(run_dir)
    report: dict[str, Any] = {
        "phase": "synthetic-dark-bell-v1-lora-training-flow",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": COMPARISON_DISCLAIMER,
        "dataset": {
            "slice_id": dataset.id,
            "name": dataset.name,
            "status": dataset.status.value,
            "manifest_path": str(manifest_path),
            "manifest_hash": manifest_hash,
            "manifest_file_hash_before": manifest_file_hash_before,
            "manifest_file_hash_after": manifest_file_hash_after,
            "immutable_after_training": frozen_manifest_immutable,
        },
        "training_run": {
            "id": run.id,
            "status": run.status.value,
            "backend": run.backend,
            "base_model_name": run.base_model_name,
            "base_model_id": run.base_model_id,
            "training_mode": run.training_mode,
            "artifact_type": run.artifact_type,
            "artifact_path": run.artifact_path,
            "style_version_id": run.style_version_id,
            "error": run.error,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        },
        "command": command,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "train_log": str(train_log_path),
        "start_time": start_time,
        "end_time": end_time,
        "returncode": returncode,
        "lora_naming": lora_naming,
        "lora_manifest_path": str(lora_manifest_path) if lora_manifest_path else None,
        "model_version": {
            "id": model_version_id,
            "created": model_version_id is not None,
            "lineage_ok": lineage_ok,
            "lineage_failures": lineage_failures,
        },
        "comparison": {
            "prompts": COMPARISON_PROMPTS,
            "seeds": COMPARISON_SEEDS,
            "pairs": comparison_pairs,
            "disclaimer": COMPARISON_DISCLAIMER,
        },
        "produced_files": produced_files,
        "comparison_ok": comparison_ok,
        "comparison_error": comparison_error,
        "success": (
            returncode == 0
            and artifact_ok
            and frozen_manifest_immutable
            and model_version_id is not None
            and lineage_ok
            and comparison_ok
        ),
        "error": error,
    }

    report_path = experiment_dir / "report.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\nSynthetic Dark Bell v1 LoRA training flow: {'PASS' if report['success'] else 'FAIL'}")
    print(f"  Training run: {run.id}  status={run.status.value}")
    print(f"  LoRA artifacts: {lora_naming['ok']}")
    print(f"  Model Version: {model_version_id}")
    print(f"  Comparison: {'ok' if comparison_ok else 'FAILED'}")
    if comparison_error:
        print(f"  Comparison error: {comparison_error}")
    print(f"  Report: {report_path}")

    return report


def _collect_files(run_dir: Path) -> list[dict[str, Any]]:
    if not run_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(p for p in run_dir.rglob("*") if p.is_file()):
        out.append({"path": str(path), "relative": str(path.relative_to(run_dir)),
                    "size_bytes": path.stat().st_size})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Synthetic Dark Bell v1 LoRA training and base-vs-LoRA comparison"
    )
    parser.add_argument("--run", action="store_true",
                        help=f"Enable real ACE training (requires {GATE_ENV}=1 or this flag)")
    parser.add_argument("--pack-dir", type=Path, default=None)
    parser.add_argument("--clip-count", type=int, default=80)
    parser.add_argument("--min-dur", type=float, default=8.0)
    parser.add_argument("--max-dur", type=float, default=15.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--train-only", action="store_true",
                        help="Run training only; skip base-vs-LoRA comparison generation")
    parser.add_argument("--allow-planned-comparison", action="store_true",
                        help="Allow comparison pairs to remain planned/skipped (no WAV validation required)")
    args = parser.parse_args()

    if not is_flow_enabled(args.run):
        print(
            f"Synthetic Dark Bell LoRA training flow is gated. "
            f"Set {GATE_ENV}=1 or pass --run to execute. No training was run."
        )
        return 0

    mandatory_comparison = not (args.train_only or args.allow_planned_comparison)
    report = verify_synthetic_lora_training_flow(
        run_training=args.run,
        pack_dir=args.pack_dir,
        clip_count=args.clip_count,
        min_dur=args.min_dur,
        max_dur=args.max_dur,
        mandatory_comparison=mandatory_comparison,
        train_only=args.train_only,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
