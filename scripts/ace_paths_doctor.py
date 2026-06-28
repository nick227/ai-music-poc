#!/usr/bin/env python3
"""Diagnose ACE-Step path configuration without modifying local files."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - lets the doctor report paths in minimal envs
    load_dotenv = None

from app.core.config import get_settings
from app.core.ace_profiles import (
    XL_SFT_CHECKPOINT,
    XL_TURBO_CHECKPOINT,
    checkpoint_layout_summary,
    xl_sft_installed,
    xl_turbo_installed,
)

LM_SAFE = "acestep-5Hz-lm-0.6B"
LM_ADVANCED = "acestep-5Hz-lm-1.7B"
TURBO_CHECKPOINT = "acestep-v15-turbo"


def _resolve(path: Path | None) -> Path | None:
    if path is None:
        return None
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded
    return (ROOT / expanded).absolute()


def _find_ace_repos(home: Path) -> list[Path]:
    repos: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(home):
        current = Path(dirpath)
        parts = set(current.parts)
        if any(part in parts for part in {".cache", ".venv", "node_modules", "__pycache__"}):
            dirnames[:] = []
            continue
        if current.name.startswith("ACE-Step") and ((current / "cli.py").is_file() or (current / "train.py").is_file()):
            repos.append(current.absolute())
            dirnames[:] = []
    return sorted(set(repos), key=str)


def _checkpoint_folders(checkpoint_dir: Path | None) -> list[str]:
    if checkpoint_dir is None or not checkpoint_dir.is_dir():
        return []
    return sorted(path.name for path in checkpoint_dir.iterdir() if path.is_dir())


def main() -> int:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()

    ace_step_dir = _resolve(settings.ace_step_dir)
    ace_python = _resolve(settings.ace_python)
    ace_model_dir = _resolve(settings.ace_model_dir)
    ace_train_checkpoint_dir = _resolve(settings.ace_train_checkpoint_dir)

    checkpoint_folders = _checkpoint_folders(ace_model_dir)
    repos = _find_ace_repos(Path.home())

    warnings: list[str] = []
    optional_notes: list[str] = []
    if ace_step_dir is None:
        warnings.append("ACE_STEP_DIR is not set.")
    elif not ace_step_dir.is_dir():
        warnings.append(f"ACE_STEP_DIR does not exist: {ace_step_dir}")

    if ace_python is None or not ace_python.is_file():
        warnings.append(f"ACE_PYTHON does not exist: {ace_python}")
    elif ace_step_dir is not None:
        expected_python = ace_step_dir / ".venv" / "bin" / "python"
        if ace_python != expected_python:
            warnings.append(f"ACE_PYTHON does not match ACE_STEP_DIR venv: expected {expected_python}")

    if ace_model_dir is None or not ace_model_dir.is_dir():
        warnings.append(f"ACE_MODEL_DIR does not exist: {ace_model_dir}")
    elif ace_step_dir is not None:
        expected_model_dir = ace_step_dir / "checkpoints"
        if ace_model_dir != expected_model_dir:
            warnings.append(f"ACE_MODEL_DIR does not match ACE_STEP_DIR/checkpoints: expected {expected_model_dir}")

    if ace_train_checkpoint_dir is None:
        warnings.append("ACE_TRAIN_CHECKPOINT_DIR is not set.")
    elif not ace_train_checkpoint_dir.is_dir():
        warnings.append(f"ACE_TRAIN_CHECKPOINT_DIR does not exist: {ace_train_checkpoint_dir}")
    elif ace_model_dir is not None and ace_train_checkpoint_dir != ace_model_dir:
        warnings.append("ACE_TRAIN_CHECKPOINT_DIR does not match ACE_MODEL_DIR.")

    if ace_model_dir is not None and ace_model_dir.is_dir():
        if not xl_sft_installed(ace_model_dir):
            optional_notes.append(
                f"optional top-model checkpoint missing ({XL_SFT_CHECKPOINT}). "
                "Turbo readiness is unaffected. Install: python scripts/install_ace_dit.py --model acestep-v15-xl-sft"
            )
        if not xl_turbo_installed(ace_model_dir):
            optional_notes.append(
                f"optional fast XL checkpoint missing ({XL_TURBO_CHECKPOINT}). "
                "Install: python scripts/install_ace_dit.py --model acestep-v15-xl-turbo"
            )

    if len(repos) > 1:
        warnings.append("Multiple ACE-Step repositories found under home.")
    if ace_step_dir is not None and repos and ace_step_dir not in repos:
        warnings.append("Configured ACE_STEP_DIR is not one of the ACE-Step repositories found under home.")

    print("== ACE Path Doctor ==")
    print(f"resolved ACE_STEP_DIR:             {ace_step_dir if ace_step_dir else '(not set)'}")
    print(f"resolved ACE_PYTHON:               {ace_python if ace_python else '(not set)'}")
    print(f"resolved ACE_MODEL_DIR:            {ace_model_dir if ace_model_dir else '(not set)'}")
    print(f"resolved ACE_TRAIN_CHECKPOINT_DIR: {ace_train_checkpoint_dir if ace_train_checkpoint_dir else '(not set)'}")
    print()
    print("checkpoint folders found:")
    if checkpoint_folders:
        for folder in checkpoint_folders:
            print(f"  - {folder}")
    else:
        print("  (none)")
    print()
    print(f"{LM_SAFE} exists:     {LM_SAFE in checkpoint_folders}")
    print(f"{LM_ADVANCED} exists: {LM_ADVANCED in checkpoint_folders}")
    print(f"{TURBO_CHECKPOINT} exists: {TURBO_CHECKPOINT in checkpoint_folders}")
    print(f"{XL_SFT_CHECKPOINT} exists: {XL_SFT_CHECKPOINT in checkpoint_folders}")
    print(f"{XL_TURBO_CHECKPOINT} exists: {XL_TURBO_CHECKPOINT in checkpoint_folders}")
    if ace_model_dir is not None:
        print(f"{TURBO_CHECKPOINT} weights: {checkpoint_layout_summary(ace_model_dir, TURBO_CHECKPOINT)}")
        print(f"{XL_SFT_CHECKPOINT} weights: {checkpoint_layout_summary(ace_model_dir, XL_SFT_CHECKPOINT)}")
        print(f"{XL_TURBO_CHECKPOINT} weights: {checkpoint_layout_summary(ace_model_dir, XL_TURBO_CHECKPOINT)}")
        print(f"{XL_SFT_CHECKPOINT} ready: {xl_sft_installed(ace_model_dir)}")
        print(f"{XL_TURBO_CHECKPOINT} ready: {xl_turbo_installed(ace_model_dir)}")
    print()
    print(f"multiple ACE-Step repos under ~: {len(repos) > 1}")
    for repo in repos:
        print(f"  - {repo}")
    print()
    print("warnings:")
    if warnings:
        for warning in warnings:
            print(f"  - {warning}")
    else:
        print("  (none)")
    print()
    print("optional notes:")
    if optional_notes:
        for note in optional_notes:
            print(f"  - {note}")
    else:
        print("  (none)")
    if warnings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
