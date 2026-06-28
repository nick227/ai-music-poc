#!/usr/bin/env python3
"""Studio → ACE-Step Training V2 runner (turbo LoRA only)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.training.ace_subprocess_env import ace_training_env

from app.training.ace_package_converter import unpack_studio_package, write_ace_dataset_json
from app.training.ace_train_commands import (
    build_preprocess_command,
    build_train_command,
    LORA_MANIFEST_NAME,
    normalize_lora_artifact,
    preprocess_command_with_shim,
    train_command_with_shim,
    resolve_lora_files,
    run_adapter_final_dir,
    run_ace_output_dir,
    run_artifacts_dir,
    run_tensors_dir,
)

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert Studio package and run ACE turbo LoRA training")
    parser.add_argument("--package", required=True, help="Path to Studio training package zip")
    parser.add_argument("--config", required=True, help="Training config JSON path")
    parser.add_argument("--output-dir", required=True, help="Training run output directory")
    parser.add_argument("--log", required=True, help="Training log file path")
    parser.add_argument("--checkpoint-dir", default=None, help="ACE checkpoint root directory")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--parent-lora", dest="parent_lora_path", default=None, help="Path to parent LoRA safetensors")
    parser.add_argument("--ace-step-dir", default=None, help="ACE-Step checkout root")
    parser.add_argument("--dry-run", action="store_true", help="Prepare commands only; do not run ACE subprocesses")
    return parser.parse_args(argv)


def _required_path_from_arg_or_env(arg_value: str | None, *env_names: str, label: str) -> Path:
    raw = arg_value.strip() if isinstance(arg_value, str) else ""
    if not raw:
        for env_name in env_names:
            raw = os.environ.get(env_name, "").strip()
            if raw:
                break
    if not raw:
        names = ", ".join(env_names)
        raise SystemExit(f"{label} is required; pass CLI arg or set one of: {names}")
    return Path(raw).expanduser().resolve()


def load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def append_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


def run_command(command: list[str], *, cwd: Path, env: dict[str, str], log_path: Path) -> int:
    append_log(log_path, f"[cmd] {' '.join(command)}")
    with log_path.open("a", encoding="utf-8") as handle:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    append_log(log_path, f"[exit] {result.returncode}")
    return result.returncode


def write_command_manifest(
    run_dir: Path,
    *,
    preprocess_command: list[str],
    train_command: list[str],
    dry_run: bool,
) -> Path:
    payload = {
        "dry_run": dry_run,
        "model_variant": "turbo",
        "preprocess_command": preprocess_command,
        "train_command": train_command,
        "artifact_final_dir": str(run_adapter_final_dir(run_dir)),
    }
    path = run_dir / "ace_train_command.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def write_artifact_manifest(artifacts_dir: Path, final_dir: Path) -> Path | None:
    normalized = normalize_lora_artifact(final_dir)
    if normalized is None:
        return None
    config_path, weights_path = resolve_lora_files(final_dir)
    payload = {
        "artifact_type": "LoRA",
        "artifact_path": "ace_output/final",
        "load_path": str(final_dir.resolve()),
        "lora_path": str(final_dir.resolve()),
        "required_files": {
            "lora_config.json": str(config_path.resolve()),
            "lora.safetensors": str(weights_path.resolve()),
        },
        "model_variant": "turbo",
    }
    path = artifacts_dir / LORA_MANIFEST_NAME
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    legacy_path = artifacts_dir / "artifact_manifest.json"
    legacy_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    package_path = Path(args.package).expanduser().resolve()
    config_path = Path(args.config).expanduser().resolve()
    run_dir = Path(args.output_dir).expanduser().resolve()
    log_path = Path(args.log).expanduser().resolve()
    ace_step_dir = _required_path_from_arg_or_env(args.ace_step_dir, "ACE_STEP_DIR", label="ACE-Step directory")
    ace_python = ace_step_dir / ".venv" / "bin" / "python"
    train_script = ace_step_dir / "train.py"
    checkpoint_dir = _required_path_from_arg_or_env(
        args.checkpoint_dir,
        "ACE_TRAIN_CHECKPOINT_DIR",
        "ACE_MODEL_DIR",
        label="ACE checkpoint directory",
    )

    config = load_config(config_path)
    run_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = run_artifacts_dir(run_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    append_log(log_path, f"[ace_train_runner] package={package_path}")
    append_log(log_path, f"[ace_train_runner] run_dir={run_dir}")

    workspace = run_dir / "workspace"
    package_root = unpack_studio_package(package_path, workspace)
    dataset_json = write_ace_dataset_json(package_root, config=config)
    tensor_dir = run_tensors_dir(run_dir)
    ace_output = run_ace_output_dir(run_dir)

    preprocess_command = preprocess_command_with_shim(
        build_preprocess_command(
            ace_python=ace_python,
            checkpoint_dir=checkpoint_dir,
            audio_dir=package_root,
            dataset_json=dataset_json,
            tensor_output=tensor_dir,
            device=args.device,
        ),
        ROOT,
    )
    train_command = train_command_with_shim(
        build_train_command(
            ace_python=ace_python,
            train_script=train_script,
            checkpoint_dir=checkpoint_dir,
            dataset_dir=tensor_dir,
            output_dir=ace_output,
            epochs=int(config.get("epochs", 1)),
            rank=int(config.get("rank", 8)),
            learning_rate=float(config.get("learning_rate", 1e-4)),
            device=args.device,
            parent_lora_path=args.parent_lora_path,
        ),
        ROOT,
    )
    write_command_manifest(
        run_dir,
        preprocess_command=preprocess_command,
        train_command=train_command,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        append_log(log_path, "[ace_train_runner] dry-run complete; no subprocess started")
        return 0

    env = ace_training_env(ace_step_dir=ace_step_dir)
    if preprocess_command:
        code = run_command(preprocess_command, cwd=ace_step_dir, env=env, log_path=log_path)
        tensor_count = len(list(tensor_dir.glob("*.pt"))) if tensor_dir.exists() else 0
        append_log(log_path, f"[ace_train_runner] preprocess exit={code} tensors={tensor_count}")
        if code != 0 or tensor_count == 0:
            return 1 if code != 0 else 1
    if train_command and run_command(train_command, cwd=ace_step_dir, env=env, log_path=log_path) != 0:
        return 2

    manifest = write_artifact_manifest(artifacts_dir, run_adapter_final_dir(run_dir))
    if manifest is None:
        append_log(log_path, "[ace_train_runner] training finished but LoRA artifacts are missing")
        return 3
    append_log(log_path, f"[ace_train_runner] artifact manifest written to {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
