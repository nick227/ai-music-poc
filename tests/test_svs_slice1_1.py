import json
from pathlib import Path

import pytest

from app.audio.vocal_energy import assert_rest_windows_silent, assert_vocal_stem_timing
from app.generators.svs import (
    GOLDEN_CASE_NAMES,
    MockSvsRenderer,
    SVS_SCORE_VERSION,
    load_svs_score,
    validate_svs_score,
    vocal_plan_to_score,
)
from app.generators.svs.models import SvsNoteEvent, SvsRestEvent, SvsScore
from app.generators.svs.music import midi_to_note_name
from app.generators.svs.validation import SvsScoreValidationError
from app.generators.vocal_plan import load_vocal_plan

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "svs_score"
VOCAL_PLAN_DIR = Path(__file__).resolve().parent / "fixtures" / "vocal_plan"


@pytest.mark.parametrize(
    ("midi", "expected"),
    [
        (60, "C4"),
        (61, "C#4"),
        (59, "B3"),
        (71, "B4"),
        (72, "C5"),
    ],
)
def test_midi_to_note_name_octave_edges(midi: int, expected: str):
    assert midi_to_note_name(midi) == expected


def test_validate_rejects_unsupported_version():
    score = SvsScore(version=2, bpm=120, duration_beats=8.0, events=[])
    with pytest.raises(SvsScoreValidationError, match="unsupported svs_score version"):
        validate_svs_score(score)


def test_validate_rejects_note_name_midi_mismatch():
    score = SvsScore(
        version=SVS_SCORE_VERSION,
        bpm=120,
        duration_beats=4.0,
        events=[
            SvsNoteEvent(
                syllable_text="la",
                phonemes=["L", "AA"],
                midi=60,
                note_name="D4",
                start_beats=0.0,
                duration_beats=1.0,
            )
        ],
    )
    with pytest.raises(SvsScoreValidationError, match="note_name"):
        validate_svs_score(score)


def test_load_svs_score_validates_golden_fixtures():
    for case_name in GOLDEN_CASE_NAMES:
        load_svs_score(FIXTURE_DIR / f"{case_name}.json")


def test_save_and_load_round_trip_validates(tmp_path: Path):
    plan = load_vocal_plan(VOCAL_PLAN_DIR / "pop_chorus.json")
    score = vocal_plan_to_score(plan)
    path = tmp_path / "score.json"
    path.write_text(score.model_dump_json(indent=2), encoding="utf-8")
    loaded = load_svs_score(path)
    assert loaded.version == SVS_SCORE_VERSION


@pytest.mark.parametrize("case_name", GOLDEN_CASE_NAMES)
def test_mock_stem_rest_energy_per_fixture(tmp_path: Path, case_name: str):
    plan = load_vocal_plan(VOCAL_PLAN_DIR / f"{case_name}.json")
    stem_path = tmp_path / f"{case_name}.wav"
    MockSvsRenderer().render(plan, stem_path=stem_path)
    assert_vocal_stem_timing(plan, stem_path)

    has_rests = any(
        line.rest_beats_after > 0 and line.syllables
        for section in plan.sections
        for line in section.lines
    )
    if has_rests:
        metrics = assert_rest_windows_silent(plan, stem_path)
        assert metrics["rest_count"] >= 1.0
        assert metrics["rest_max_rms"] <= 0.0025


def test_golden_fixture_scores_match_rebuilt_export():
    for case_name in GOLDEN_CASE_NAMES:
        golden = json.loads((FIXTURE_DIR / f"{case_name}.json").read_text(encoding="utf-8"))
        plan = load_vocal_plan(VOCAL_PLAN_DIR / f"{case_name}.json")
        rebuilt = vocal_plan_to_score(plan).model_dump()
        assert rebuilt == golden


def test_validate_rejects_out_of_order_events():
    score = SvsScore(
        version=SVS_SCORE_VERSION,
        bpm=120,
        duration_beats=8.0,
        events=[
            SvsNoteEvent(
                syllable_text="a",
                phonemes=["AH"],
                midi=60,
                note_name="C4",
                start_beats=2.0,
                duration_beats=0.5,
            ),
            SvsRestEvent(start_beats=1.0, duration_beats=0.25),
        ],
    )
    with pytest.raises(SvsScoreValidationError, match="non-decreasing"):
        validate_svs_score(score)
