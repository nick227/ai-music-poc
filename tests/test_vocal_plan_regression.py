"""Regression tests for VocalPlan timing bugs."""

from app.generators.vocal_plan import build_vocal_plan, syllable_at

SCALE = [0, 2, 4, 5, 7, 9, 11]
ROOT_HZ = 261.63


def _pop_plan():
    return build_vocal_plan(
        """Verse:
I walk alone beneath the city lights
Chorus:
We rise tonight we shine so bright""",
        bpm=118,
        key="C",
        duration_beats=48.0,
        scale=SCALE,
        root_hz=ROOT_HZ,
        profile_name="pop",
    )


def test_regression_syllable_at_none_during_planned_rests():
    plan = _pop_plan()
    for section in plan.sections:
        for line in section.lines:
            if line.rest_beats_after <= 0 or not line.syllables:
                continue
            last = line.syllables[-1]
            rest_start = last.beat_start + last.beat_duration
            for offset in (0.2, 0.5, 0.8):
                beat_pos = rest_start + line.rest_beats_after * offset
                assert syllable_at(plan, beat_pos) is None, f"rest at {beat_pos:.2f} should be silent"


def test_regression_syllable_at_none_after_vocal_end_beat():
    plan = _pop_plan()
    for beat_pos in (
        plan.vocal_end_beat(),
        plan.vocal_end_beat() + 0.25,
        plan.vocal_end_beat() + 4.0,
        plan.duration_beats + 2.0,
    ):
        assert syllable_at(plan, beat_pos) is None, f"post-plan beat {beat_pos:.2f} should be silent"


def test_regression_syllable_at_does_not_wrap_to_first_syllable():
    plan = build_vocal_plan(
        "hello world",
        bpm=120,
        key=None,
        duration_beats=32.0,
        scale=SCALE,
        root_hz=ROOT_HZ,
    )
    far_beat = plan.vocal_end_beat() + 1.0
    assert syllable_at(plan, far_beat) is None
    first = plan.flat_syllables()[0]
    hit = syllable_at(plan, first.beat_start + 0.01)
    assert hit is not None
    assert hit[0].text == first.text
