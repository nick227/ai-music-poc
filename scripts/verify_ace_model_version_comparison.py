#!/usr/bin/env python3
"""Phase 5 proof: paired base-vs-trained ACE generation comparison."""

from __future__ import annotations

import argparse
import json
import os
import re
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

from app.core.ace_runtime import validate_with_ffprobe
from app.core.audio_validation import validate_wav_output
from app.core.config import get_settings
from app.domain.models import JobStatus
from app.storage.slice_store import SliceStore
from app.storage.style_version_store import StyleVersionStore
from app.storage.training_run_store import TrainingRunStore
from app.training.ace_train_commands import required_adapter_files

DEFAULT_TRAINING_RUN_ID = "train_69be1faca5b9490fa4a6cffa1a15ab90"
DEFAULT_MODEL_VERSION_ID = "style_d09c797de64c4873856ed4506c80b9e3"
PROMPTS = [
    "soft bell texture, sparse ambient chimes, cinematic",
    "minimal metallic bell pulses, quiet room tone",
    "dreamy ambient soundscape with small bell accents",
]
SEEDS = [101, 202, 303]
RUNTIME_CONFIG = {
    "duration": 10,
    "checkpoint": "acestep-v15-turbo",
    "lm_model": "acestep-5Hz-lm-0.6B",
    "steps": 8,
    "batch": 1,
    "offload_to_cpu": True,
    "quality": "draft",
    "guidance_scale": 7.5,
    "lora_scale": 1.0,
}


def slugify(value: str, *, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:max_len].strip("-") or "prompt"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _path_from_artifact(data_dir: Path, artifact_path: str) -> Path:
    path = Path(artifact_path)
    if path.is_absolute():
        return path
    return data_dir / path


def validate_adapter_package(adapter_dir: Path, training_run_dir: Path) -> dict[str, Any]:
    config_path, weights_path = required_adapter_files(adapter_dir)
    manifest_path = training_run_dir / "artifacts" / "artifact_manifest.json"
    files = {
        "adapter_config.json": config_path,
        "adapter_model.safetensors": weights_path,
        "artifact_manifest.json": manifest_path,
    }
    details: dict[str, dict[str, Any]] = {}
    for name, path in files.items():
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
        details[name] = {
            "path": str(path),
            "exists": exists,
            "size_bytes": size,
            "nonzero": size > 0,
        }
    return {
        "adapter_dir": str(adapter_dir),
        "files": details,
        "ok": adapter_dir.is_dir() and all(item["exists"] and item["nonzero"] for item in details.values()),
    }


def build_generation_pairs(prompts: list[str] | None = None, seeds: list[int] | None = None) -> list[dict[str, Any]]:
    prompts = prompts or PROMPTS
    seeds = seeds or SEEDS
    pairs: list[dict[str, Any]] = []
    for prompt_index, prompt in enumerate(prompts, start=1):
        for seed in seeds:
            stem = f"p{prompt_index:02d}-seed-{seed}-{slugify(prompt)}"
            pairs.append({"prompt_index": prompt_index, "prompt": prompt, "seed": seed, "stem": stem})
    return pairs


def validate_generated_audio(path: Path, *, ffprobe: str = "ffprobe", min_duration_seconds: float = 8.0) -> dict[str, Any]:
    probe = validate_with_ffprobe(path, ffprobe=ffprobe)
    payload = probe.model_dump()
    payload["duration_at_least_8s"] = probe.duration_seconds >= min_duration_seconds
    payload["nonzero_size"] = probe.file_size_bytes > 0
    payload["ok"] = bool(probe.ok and payload["duration_at_least_8s"] and payload["nonzero_size"])
    try:
        wav = validate_wav_output(path, expected_duration_seconds=RUNTIME_CONFIG["duration"])
        payload["rms"] = wav.rms
        payload["peak_abs_sample"] = wav.peak_abs_sample
        payload["wav_warnings"] = wav.warnings
    except Exception as exc:
        payload["rms"] = None
        payload["peak_abs_sample"] = None
        payload["wav_warnings"] = [str(exc)]
    return payload


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_generation_command(
    *,
    ace_python: Path,
    ace_script: Path,
    prompt_file: Path,
    lyrics_file: Path,
    output_path: Path,
    model_dir: Path,
    device: str,
    seed: int,
    use_lora: bool,
    adapter_dir: Path | None,
) -> list[str]:
    return [
        str(ace_python),
        str(ace_script),
        "--prompt-file",
        str(prompt_file),
        "--lyrics-file",
        str(lyrics_file),
        "--output",
        str(output_path),
        "--model-dir",
        str(model_dir),
        "--duration",
        str(RUNTIME_CONFIG["duration"]),
        "--seed",
        str(seed),
        "--guidance-scale",
        str(RUNTIME_CONFIG["guidance_scale"]),
        "--quality",
        str(RUNTIME_CONFIG["quality"]),
        "--device",
        device,
        "--offload-to-cpu",
        "--use-lm",
        "true",
        "--lm-model",
        str(RUNTIME_CONFIG["lm_model"]),
        "--use-lora",
        "true" if use_lora else "false",
        "--lora-path",
        str(adapter_dir) if use_lora and adapter_dir is not None else "__none__",
        "--lora-scale",
        str(RUNTIME_CONFIG["lora_scale"]),
    ]


def _run_generation(command: list[str], *, env: dict[str, str], stdout_path: Path, stderr_path: Path, timeout: int) -> int:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            result = subprocess.run(
                command,
                cwd=str(ROOT),
                env=env,
                stdout=stdout,
                stderr=stderr,
                text=True,
                timeout=timeout,
                check=False,
            )
        return result.returncode
    except subprocess.TimeoutExpired as exc:
        stderr_path.write_text(f"Timed out after {exc.timeout} seconds\n", encoding="utf-8")
        return 124


def _lora_meta(output_path: Path) -> dict[str, Any]:
    meta_path = output_path.with_name(f"{output_path.stem}.ace_meta.json")
    if not meta_path.is_file():
        return {}
    try:
        return _read_json(meta_path)
    except json.JSONDecodeError:
        return {}


def _manual_checklist() -> list[str]:
    return [
        "Listen to each base/trained pair at matched loudness.",
        "Check whether trained clips contain more bell-like transients or metallic decays.",
        "Check whether non-bell ambience, timing, and mix quality remain acceptable.",
        "Mark any pair where LoRA loading succeeded but the trained output is worse or unchanged.",
        "Do not treat this report as an automatic quality win; it only proves paired generation succeeded.",
    ]


def _write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# ACE Model Version Comparison",
        "",
        "This report proves comparable base and trained/LoRA generations completed. It does not claim quality improvement.",
        "",
        f"- Model Version: `{report['model_version_id']}`",
        f"- Training Run: `{report['training_run_id']}`",
        f"- Frozen Dataset: `{report['frozen_dataset_id']}`",
        f"- Frozen Manifest Hash: `{report['frozen_dataset_manifest_hash']}`",
        f"- Adapter: `{report['adapter_artifact_path']}`",
        "",
        "## Manual Listening Checklist",
        "",
    ]
    lines.extend(f"- {item}" for item in report["manual_listening_checklist"])
    lines.extend(["", "## Pairs", ""])
    for pair in report["pairs"]:
        lines.extend(
            [
                f"### {pair['stem']}",
                "",
                f"- Prompt: {pair['prompt']}",
                f"- Seed: `{pair['seed']}`",
                f"- Base: `{pair['base']['output_path']}`",
                f"- Trained: `{pair['trained']['output_path']}`",
                f"- Base OK: `{pair['base']['audio']['ok']}`",
                f"- Trained OK: `{pair['trained']['audio']['ok']}`",
                f"- LoRA loaded: `{pair['trained'].get('lora_meta', {}).get('loraLoadSucceeded')}`",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def verify_ace_model_version_comparison(
    *,
    model_version_id: str = DEFAULT_MODEL_VERSION_ID,
    training_run_id: str = DEFAULT_TRAINING_RUN_ID,
    prompts: list[str] | None = None,
    seeds: list[int] | None = None,
) -> dict[str, Any]:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()

    style_store = StyleVersionStore(settings.style_versions_dir)
    run_store = TrainingRunStore(settings.training_runs_dir)
    slice_store = SliceStore(settings.slices_dir)
    model_version = style_store.get(model_version_id)
    if model_version is None:
        raise RuntimeError(f"Model Version not found: {model_version_id}")
    if model_version.training_run_id != training_run_id:
        raise RuntimeError(f"Model Version points to {model_version.training_run_id}, expected {training_run_id}")
    training_run = run_store.get(training_run_id)
    if training_run is None:
        raise RuntimeError(f"TrainingRun not found: {training_run_id}")
    if training_run.status != JobStatus.SUCCEEDED:
        raise RuntimeError(f"TrainingRun is not SUCCEEDED: {training_run.status}")
    if training_run.style_version_id != model_version.id:
        raise RuntimeError("TrainingRun style_version_id does not point back to Model Version")
    if not training_run.artifact_path:
        raise RuntimeError("TrainingRun has no artifact_path")

    adapter_dir = _path_from_artifact(settings.data_dir, training_run.artifact_path)
    adapter_validation = validate_adapter_package(adapter_dir, run_store.run_dir(training_run.id))
    if not adapter_validation["ok"]:
        raise RuntimeError(f"Adapter package validation failed: {adapter_validation}")

    dataset = slice_store.get(training_run.dataset_slice_id)
    if dataset is None:
        raise RuntimeError(f"Frozen dataset not found: {training_run.dataset_slice_id}")
    manifest_path = settings.slices_dir / dataset.id / "manifest.json"
    frozen_manifest = _read_json(manifest_path)
    frozen_manifest_hash = str(frozen_manifest.get("manifest_hash") or "")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    experiment_dir = settings.data_dir / "experiments" / "ace-model-version-comparison" / timestamp
    outputs_dir = experiment_dir / "outputs"
    requests_dir = experiment_dir / "requests"
    logs_dir = experiment_dir / "logs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    requests_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    if settings.ace_step_dir is not None:
        env["ACE_STEP_DIR"] = str(settings.ace_step_dir.expanduser())
    env["ACE_MODEL_DIR"] = str(settings.ace_model_dir.expanduser())
    env["ACE_TRAIN_CHECKPOINT_DIR"] = str((settings.ace_train_checkpoint_dir or settings.ace_model_dir).expanduser())

    pairs_report: list[dict[str, Any]] = []
    for pair in build_generation_pairs(prompts=prompts, seeds=seeds):
        prompt_file = requests_dir / f"{pair['stem']}.prompt.txt"
        lyrics_file = requests_dir / f"{pair['stem']}.lyrics.txt"
        _write_text(prompt_file, pair["prompt"])
        _write_text(lyrics_file, "")

        pair_payload: dict[str, Any] = {
            "prompt_index": pair["prompt_index"],
            "prompt": pair["prompt"],
            "seed": pair["seed"],
            "stem": pair["stem"],
        }
        for variant, use_lora in [("base", False), ("trained", True)]:
            output_path = outputs_dir / f"{pair['stem']}-{variant}.wav"
            stdout_path = logs_dir / f"{pair['stem']}-{variant}.stdout.log"
            stderr_path = logs_dir / f"{pair['stem']}-{variant}.stderr.log"
            command = _build_generation_command(
                ace_python=settings.ace_python,
                ace_script=(ROOT / "scripts" / "ace_runner.py").resolve(),
                prompt_file=prompt_file,
                lyrics_file=lyrics_file,
                output_path=output_path,
                model_dir=settings.ace_model_dir,
                device=settings.ace_device,
                seed=int(pair["seed"]),
                use_lora=use_lora,
                adapter_dir=adapter_dir,
            )
            started_at = datetime.now(timezone.utc).isoformat()
            returncode = _run_generation(
                command,
                env=env,
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                timeout=settings.ace_timeout_seconds,
            )
            finished_at = datetime.now(timezone.utc).isoformat()
            audio = validate_generated_audio(output_path, ffprobe="ffprobe")
            pair_payload[variant] = {
                "output_path": str(output_path),
                "stdout_log_path": str(stdout_path),
                "stderr_log_path": str(stderr_path),
                "command": command,
                "started_at": started_at,
                "finished_at": finished_at,
                "returncode": returncode,
                "audio": audio,
                "lora_meta": _lora_meta(output_path),
                "success": returncode == 0 and bool(audio["ok"]),
            }
        pairs_report.append(pair_payload)

    all_base_ok = all(pair["base"]["success"] for pair in pairs_report)
    all_trained_ok = all(pair["trained"]["success"] for pair in pairs_report)
    all_trained_lora_loaded = all(pair["trained"].get("lora_meta", {}).get("loraLoadSucceeded") is True for pair in pairs_report)
    report = {
        "phase": "phase-5-ace-model-version-comparison",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "model_version_id": model_version.id,
        "training_run_id": training_run.id,
        "adapter_artifact_path": str(adapter_dir / "adapter_model.safetensors"),
        "adapter_dir": str(adapter_dir),
        "adapter_validation": adapter_validation,
        "frozen_dataset_id": dataset.id,
        "frozen_dataset_name": dataset.name,
        "frozen_dataset_manifest_hash": frozen_manifest_hash,
        "frozen_dataset_manifest_path": str(manifest_path),
        "runtime_config": {
            **RUNTIME_CONFIG,
            "device": settings.ace_device,
            "model_dir": str(settings.ace_model_dir),
            "ace_step_dir": str(settings.ace_step_dir) if settings.ace_step_dir else "",
            "ace_python": str(settings.ace_python),
        },
        "pairs": pairs_report,
        "summary": {
            "pair_count": len(pairs_report),
            "base_generations_succeeded": all_base_ok,
            "trained_generations_succeeded": all_trained_ok,
            "trained_lora_load_succeeded": all_trained_lora_loaded,
            "all_audio_valid": all(
                pair["base"]["audio"]["ok"] and pair["trained"]["audio"]["ok"] for pair in pairs_report
            ),
            "quality_claim": "none; manual listening required",
        },
        "manual_listening_checklist": _manual_checklist(),
        "success": all_base_ok and all_trained_ok and all_trained_lora_loaded,
    }
    report_path = experiment_dir / "report.json"
    markdown_path = experiment_dir / "report.md"
    report["report_path"] = str(report_path)
    report["markdown_report_path"] = str(markdown_path)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_markdown_report(report, markdown_path)

    if not report["success"]:
        raise RuntimeError(f"ACE model version comparison failed; report written to {report_path}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate paired base-vs-trained ACE outputs for Phase 5")
    parser.add_argument("--model-version-id", default=DEFAULT_MODEL_VERSION_ID)
    parser.add_argument("--training-run-id", default=DEFAULT_TRAINING_RUN_ID)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = verify_ace_model_version_comparison(
        model_version_id=args.model_version_id,
        training_run_id=args.training_run_id,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("ACE model version comparison: PASS")
        print(f"Model Version: {report['model_version_id']}")
        print(f"Training Run: {report['training_run_id']}")
        print(f"Pairs: {report['summary']['pair_count']}")
        print(f"Report: {report['report_path']}")
        print(f"Markdown: {report['markdown_report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
