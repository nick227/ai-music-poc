"""Measurable audio regression tests for vocal timing."""

from pathlib import Path

import pytest

from app.audio.vocal_energy import assert_vocal_stem_timing, max_abs_sample, read_mono_wav_normalized
from app.domain.models import GenerationRequest
from app.generators.procedural import ProceduralGenerator
from app.generators.vocal_plan import load_vocal_plan
from scripts.regenerate_vocal_listen_demos import DEMO_CASES

DRAFT_CASE_NAMES = tuple(name for name, _, _ in DEMO_CASES)


def _render_case(tmp_path: Path, case_name: str, *, quality: str) -> tuple[Path, Path]:
    demo = next(item for item in DEMO_CASES if item[0] == case_name)
    name, prompt, lyrics = demo
    generator = ProceduralGenerator()
    request = GenerationRequest.model_validate(
        {
            "title": name,
            "prompt": prompt,
            "lyrics": lyrics,
            "duration_seconds": 10,
            "quality": quality,
            "mode": "song",
            "vocal_intensity": 0.65,
            "vocal_style": "ballad held legato" if name == "ballad_held" else None,
            "seed": 42,
        }
    )
    wav_path = tmp_path / f"{case_name}.wav"
    result = generator.generate(request, wav_path)
    plan_path = wav_path.with_name(result.metadata["vocal_plan_file"])
    stem_path = wav_path.with_name(result.metadata["vocal_stem_file"])
    return plan_path, stem_path


@pytest.fixture()
def pop_high_render(tmp_path: Path) -> tuple[Path, Path, Path]:
    plan_path, stem_path = _render_case(tmp_path, "pop_chorus", quality="high")
    return plan_path, stem_path, tmp_path / "pop_chorus.wav"


def test_vocal_stem_louder_during_syllables_than_rests(pop_high_render: tuple[Path, Path, Path]):
    plan_path, stem_path, _ = pop_high_render
    plan = load_vocal_plan(plan_path)
    metrics = assert_vocal_stem_timing(plan, stem_path)
    assert metrics["syllable_median_rms"] > metrics["rest_max_rms"] * 2.0


def test_full_mix_has_non_silent_audio_and_no_clipping(pop_high_render: tuple[Path, Path, Path]):
    plan_path, _, mix_path = pop_high_render
    _ = load_vocal_plan(plan_path)
    samples, _ = read_mono_wav_normalized(mix_path)
    assert max_abs_sample(samples) <= 1.0
    assert max_abs_sample(samples) > 0.05


@pytest.mark.parametrize("case_name", DRAFT_CASE_NAMES)
def test_procedural_golden_case_vocal_stem_respects_plan_timing(tmp_path: Path, case_name: str):
    # balanced exports vocal stem; draft uses the same VocalPlan + renderer path
    plan_path, stem_path = _render_case(tmp_path, case_name, quality="balanced")
    plan = load_vocal_plan(plan_path)
    metrics = assert_vocal_stem_timing(plan, stem_path)
    assert metrics["syllable_median_rms"] > metrics["rest_max_rms"]
