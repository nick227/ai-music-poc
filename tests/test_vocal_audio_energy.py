"""Measurable audio regression tests for vocal timing."""

from pathlib import Path

import pytest

from app.audio.vocal_energy import assert_vocal_stem_timing, max_abs_sample, read_mono_wav_normalized
from app.domain.models import GenerationRequest
from app.generators.procedural import ProceduralGenerator
from app.generators.vocal_plan import load_vocal_plan

SCALE = [0, 2, 4, 5, 7, 9, 11]
ROOT_HZ = 261.63

POP_LYRICS = """Verse:
I walk alone beneath the city lights
Chorus:
We rise tonight we shine so bright"""


@pytest.fixture()
def pop_high_render(tmp_path: Path) -> tuple[Path, Path, Path]:
    generator = ProceduralGenerator()
    request = GenerationRequest.model_validate(
        {
            "title": "Energy Test",
            "prompt": "bright pop chorus hook glossy drums",
            "lyrics": POP_LYRICS,
            "duration_seconds": 10,
            "quality": "high",
            "mode": "song",
            "vocal_intensity": 0.65,
            "seed": 7,
        }
    )
    wav_path = tmp_path / "energy.wav"
    result = generator.generate(request, wav_path)
    plan_path = wav_path.with_name(result.metadata["vocal_plan_file"])
    stem_path = wav_path.with_name(result.metadata["vocal_stem_file"])
    return plan_path, stem_path, wav_path


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
