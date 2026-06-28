"""ACE GenerationParams presets aligned with Gradio model-type defaults."""
from __future__ import annotations


def is_turbo_checkpoint(checkpoint: str) -> bool:
    lower = checkpoint.lower()
    return "turbo" in lower


def is_sft_checkpoint(checkpoint: str) -> bool:
    lower = checkpoint.lower()
    return "sft" in lower and "turbo" not in lower


def resolve_inference_steps(*, checkpoint: str, requested: int | None = None) -> int:
    if requested is not None:
        return requested
    if is_turbo_checkpoint(checkpoint):
        return 8
    if is_sft_checkpoint(checkpoint):
        return 50
    return 32


def build_generation_params_kwargs(
    *,
    checkpoint: str,
    caption: str,
    lyrics: str,
    duration: int,
    seed: int,
    inference_steps: int | None = None,
    use_lm: bool = False,
) -> dict[str, object]:
    """Kwargs for acestep.inference.GenerationParams matching Gradio per model type."""
    steps = resolve_inference_steps(checkpoint=checkpoint, requested=inference_steps)
    instrumental = lyrics.strip().lower() in {"[instrumental]", "[inst]"}
    if is_turbo_checkpoint(checkpoint):
        return {
            "task_type": "text2music",
            "caption": caption,
            "lyrics": lyrics,
            "instrumental": instrumental,
            "duration": duration,
            "inference_steps": min(steps, 8),
            "seed": seed,
            "guidance_scale": 1.0,
            "shift": 3.0,
            "dcw_enabled": True,
            "thinking": use_lm,
            "enable_normalization": True,
            "normalization_db": -1.0,
        }
    return {
        "task_type": "text2music",
        "caption": caption,
        "lyrics": lyrics,
        "instrumental": instrumental,
        "duration": duration,
        "inference_steps": steps,
        "seed": seed,
        "guidance_scale": 7.0,
        "shift": 3.0,
        "use_adg": False,
        "cfg_interval_start": 0.0,
        "cfg_interval_end": 1.0,
        "dcw_enabled": False,
        "thinking": use_lm,
        "enable_normalization": True,
        "normalization_db": -1.0,
    }
