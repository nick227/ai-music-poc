"""Resolve ACE DiT checkpoint and step count from quality tier and installed models."""
from __future__ import annotations

from pathlib import Path

from app.core.ace_profiles import (
    SAFE_TURBO_CHECKPOINT,
    XL_SFT_APP_ENABLED,
    XL_SFT_CHECKPOINT,
    xl_sft_installed,
)

_TURBO_NAMES = [SAFE_TURBO_CHECKPOINT, "acestep-v1-turbo", "acestep-v1"]
_XL_SFT_NAMES = [XL_SFT_CHECKPOINT]
_QUALITY_STEPS = {"draft": 8, "balanced": 24, "high": 50}
_TURBO_MAX_STEPS = 8


def list_checkpoint_dirs(checkpoint_dir: Path) -> set[str]:
    if not checkpoint_dir.is_dir():
        return set()
    return {p.name for p in checkpoint_dir.iterdir() if p.is_dir()}


def resolve_generation_plan(*, quality: str, checkpoint_dir: Path) -> tuple[str, int, bool]:
    """Return (config_path, inference_steps, is_turbo_checkpoint).

    App generation always uses 2B turbo today. XL SFT is opt-in via compare script only
    until XL_SFT_APP_ENABLED is flipped after listening validation.
    """
    entries = list_checkpoint_dirs(checkpoint_dir)
    turbo = next((n for n in _TURBO_NAMES if n in entries), SAFE_TURBO_CHECKPOINT)
    requested_steps = _QUALITY_STEPS.get(quality, 24)

    if (
        XL_SFT_APP_ENABLED
        and xl_sft_installed(checkpoint_dir)
        and quality in ("balanced", "high")
    ):
        xl_sft = next((n for n in _XL_SFT_NAMES if n in entries), "")
        if xl_sft:
            return xl_sft, requested_steps, False

    return turbo, min(requested_steps, _TURBO_MAX_STEPS), True
