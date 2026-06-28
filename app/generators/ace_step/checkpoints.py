"""Resolve ACE DiT checkpoint and step count from quality tier and installed models."""
from __future__ import annotations

from pathlib import Path

_SFT_NAMES = ["acestep-v15-sft", "acestep-v15-base"]
_TURBO_NAMES = ["acestep-v15-turbo", "acestep-v1-turbo", "acestep-v1"]
_QUALITY_STEPS = {"draft": 8, "balanced": 24, "high": 50}
_TURBO_MAX_STEPS = 8


def list_checkpoint_dirs(checkpoint_dir: Path) -> set[str]:
    if not checkpoint_dir.is_dir():
        return set()
    return {p.name for p in checkpoint_dir.iterdir() if p.is_dir()}


def resolve_generation_plan(*, quality: str, checkpoint_dir: Path) -> tuple[str, int, bool]:
    """Return (config_path, inference_steps, is_turbo_checkpoint)."""
    entries = list_checkpoint_dirs(checkpoint_dir)
    turbo = next((n for n in _TURBO_NAMES if n in entries), "acestep-v15-turbo")
    sft = next((n for n in _SFT_NAMES if n in entries), "")
    requested_steps = _QUALITY_STEPS.get(quality, 24)

    if sft and quality in ("balanced", "high"):
        return sft, requested_steps, False

    return turbo, min(requested_steps, _TURBO_MAX_STEPS), True
