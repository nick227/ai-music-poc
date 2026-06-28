from app.generators.ace_step.inference_presets import (
    build_generation_params_kwargs,
    is_sft_checkpoint,
    is_turbo_checkpoint,
    resolve_inference_steps,
)


def test_turbo_preset() -> None:
    kw = build_generation_params_kwargs(
        checkpoint="acestep-v15-turbo",
        caption="test",
        lyrics="[Instrumental]",
        duration=15,
        seed=1,
    )
    assert kw["inference_steps"] == 8
    assert kw["dcw_enabled"] is True
    assert kw["guidance_scale"] == 1.0


def test_sft_preset_matches_gradio() -> None:
    kw = build_generation_params_kwargs(
        checkpoint="acestep-v15-xl-sft",
        caption="test",
        lyrics="[Instrumental]",
        duration=15,
        seed=1,
    )
    assert kw["inference_steps"] == 50
    assert kw["dcw_enabled"] is False
    assert kw["guidance_scale"] == 7.0
    assert kw["shift"] == 3.0
    assert is_sft_checkpoint("acestep-v15-xl-sft")
    assert not is_turbo_checkpoint("acestep-v15-xl-sft")


def test_resolve_steps_override() -> None:
    assert resolve_inference_steps(checkpoint="acestep-v15-xl-sft", requested=24) == 24
