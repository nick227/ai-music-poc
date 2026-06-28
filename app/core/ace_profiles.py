"""Named ACE render profiles — turbo safe default, XL experimental top model."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from app.core.ace_checkpoint_layout import describe_checkpoint_layout, dit_checkpoint_ready

SAFE_TURBO_CHECKPOINT = "acestep-v15-turbo"
XL_SFT_CHECKPOINT = "acestep-v15-xl-sft"
XL_TURBO_CHECKPOINT = "acestep-v15-xl-turbo"
PROFILE_LM = "acestep-5Hz-lm-0.6B"

FINAL_XL_SFT_24 = "final_xl_sft_24"
FINAL_XL_SFT_50 = "final_xl_sft_50"
XL_TURBO_8 = "xl_turbo_8"


class AceRenderProfile(BaseModel):
    name: str
    checkpoint: str
    inference_steps: int
    batch_size: int = 1
    offload_to_cpu: bool = True
    lm_model: str = ""
    description: str = ""


def checkpoint_has_weights(checkpoint_dir: Path, name: str) -> bool:
    return dit_checkpoint_ready(checkpoint_dir, name)


def xl_sft_installed(checkpoint_dir: Path) -> bool:
    return checkpoint_has_weights(checkpoint_dir, XL_SFT_CHECKPOINT)


def xl_turbo_installed(checkpoint_dir: Path) -> bool:
    return checkpoint_has_weights(checkpoint_dir, XL_TURBO_CHECKPOINT)


def checkpoint_layout_summary(checkpoint_dir: Path, name: str) -> str:
    return describe_checkpoint_layout(checkpoint_dir / name)


def build_xl_sft_profile(*, inference_steps: int) -> AceRenderProfile:
    name = FINAL_XL_SFT_24 if inference_steps == 24 else FINAL_XL_SFT_50
    return AceRenderProfile(
        name=name,
        checkpoint=XL_SFT_CHECKPOINT,
        inference_steps=inference_steps,
        batch_size=1,
        offload_to_cpu=True,
        lm_model=PROFILE_LM,
        description=(
            f"Experimental XL final-render — {XL_SFT_CHECKPOINT}, "
            f"{inference_steps} steps, batch=1, offload=true, lm={PROFILE_LM}"
        ),
    )


def build_xl_turbo_profile() -> AceRenderProfile:
    return AceRenderProfile(
        name=XL_TURBO_8,
        checkpoint=XL_TURBO_CHECKPOINT,
        inference_steps=8,
        batch_size=1,
        offload_to_cpu=True,
        lm_model=PROFILE_LM,
        description=(
            f"Optional fast XL — {XL_TURBO_CHECKPOINT}, "
            f"8 steps, batch=1, offload=true, lm={PROFILE_LM}"
        ),
    )


def build_final_render_profiles(checkpoint_dir: Path) -> list[AceRenderProfile]:
    """Return XL top-model profiles when acestep-v15-xl-sft is on disk."""
    profiles: list[AceRenderProfile] = []
    if xl_sft_installed(checkpoint_dir):
        profiles.append(build_xl_sft_profile(inference_steps=24))
        profiles.append(build_xl_sft_profile(inference_steps=50))
    if xl_turbo_installed(checkpoint_dir):
        profiles.append(build_xl_turbo_profile())
    return profiles
