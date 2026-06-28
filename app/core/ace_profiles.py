"""Named ACE render profiles for experimental / final-quality generation."""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

FINAL_SFT_NAME = "final_sft"
FINAL_SFT_CHECKPOINT = "acestep-v15-sft"
FINAL_SFT_LM = "acestep-5Hz-lm-0.6B"
FINAL_SFT_STEP_OPTIONS = (24, 50)


class AceRenderProfile(BaseModel):
    name: str
    checkpoint: str
    inference_steps: int
    batch_size: int = 1
    offload_to_cpu: bool = True
    lm_model: str = ""
    description: str = ""


def checkpoint_has_weights(checkpoint_dir: Path, name: str) -> bool:
    return (checkpoint_dir / name / "model.safetensors").is_file()


def final_sft_installed(checkpoint_dir: Path) -> bool:
    return checkpoint_has_weights(checkpoint_dir, FINAL_SFT_CHECKPOINT)


def build_final_sft_profile(*, inference_steps: int) -> AceRenderProfile:
    return AceRenderProfile(
        name=FINAL_SFT_NAME,
        checkpoint=FINAL_SFT_CHECKPOINT,
        inference_steps=inference_steps,
        batch_size=1,
        offload_to_cpu=True,
        lm_model=FINAL_SFT_LM,
        description=(
            f"Experimental final-render — {FINAL_SFT_CHECKPOINT}, "
            f"{inference_steps} steps, batch=1, offload=true, lm={FINAL_SFT_LM}"
        ),
    )


def build_final_render_profiles(checkpoint_dir: Path) -> list[AceRenderProfile]:
    """Return final_sft profiles (24 and 50 steps) when acestep-v15-sft is on disk."""
    if not final_sft_installed(checkpoint_dir):
        return []
    return [build_final_sft_profile(inference_steps=steps) for steps in FINAL_SFT_STEP_OPTIONS]
