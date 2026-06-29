import json
from pathlib import Path

import pytest

from app.audio.vocal_energy import assert_vocal_stem_timing
from app.generators.svs import GOLDEN_CASE_NAMES, MockSvsRenderer, vocal_plan_to_score
from app.generators.svs.g2p_en import syllable_to_phonemes
from app.generators.vocal_plan import build_vocal_plan, load_vocal_plan, vocal_plan_timing_for

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "svs_score"
VOCAL_PLAN_DIR = Path(__file__).resolve().parent / "fixtures" / "vocal_plan"
SCALE = [0, 2, 4, 5, 7, 9, 11]
ROOT_HZ = 261.63
GOLDEN_CASES = GOLDEN_CASE_NAMES


def _load_vocal_plan_case(name: str):
    return load_vocal_plan(VOCAL_PLAN_DIR / f"{name}.json")


def _load_score_fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _rebuild_score(name: str) -> dict:
    plan = _load_vocal_plan_case(name)
    return vocal_plan_to_score(plan).model_dump()


def test_g2p_returns_phonemes_for_syllable():
    assert syllable_to_phonemes("walk") == ["W", "AE", "L", "K"]
    assert syllable_to_phonemes("the") == ["TH", "EH"]


@pytest.mark.parametrize("case_name", GOLDEN_CASES)
def test_golden_svs_score_matches_fixture(case_name: str):
    golden = _load_score_fixture(case_name)
    rebuilt = _rebuild_score(case_name)
    assert rebuilt == golden


@pytest.mark.parametrize("case_name", GOLDEN_CASES)
def test_score_event_counts_match_vocal_plan(case_name: str):
    plan = _load_vocal_plan_case(case_name)
    score = vocal_plan_to_score(plan)
    syllable_count = plan.syllable_count()
    rest_count = sum(
        1
        for section in plan.sections
        for line in section.lines
        if line.rest_beats_after > 0 and line.syllables
    )
    assert len(score.note_events()) == syllable_count
    assert len(score.rest_events()) == rest_count
    assert score.note_events()[0].note_name
    assert score.note_events()[0].phonemes


def test_score_from_rebuilt_plan_matches_fixture_case():
    cases = json.loads((VOCAL_PLAN_DIR / "cases.json").read_text(encoding="utf-8"))
    case = cases["pop_chorus"]
    plan = build_vocal_plan(
        case["lyrics"],
        bpm=case["bpm"],
        key=case["key"],
        duration_beats=case["duration_beats"],
        scale=SCALE,
        root_hz=ROOT_HZ,
        profile_name=case["profile_name"],
        timing=vocal_plan_timing_for(case["profile_name"], case.get("vocal_style")),
    )
    score = vocal_plan_to_score(plan)
    fixture = _load_score_fixture("pop_chorus")
    assert score.model_dump() == fixture


@pytest.mark.parametrize("case_name", GOLDEN_CASES)
def test_mock_renderer_writes_score_and_stem(tmp_path: Path, case_name: str):
    plan = _load_vocal_plan_case(case_name)
    stem_path = tmp_path / f"{case_name}_mock_vocal.wav"
    renderer = MockSvsRenderer()
    result = renderer.render(plan, stem_path=stem_path)
    assert result.backend == "svs-mock"
    assert result.score_path.exists()
    assert stem_path.exists()
    assert stem_path.stat().st_size > 1000
    assert result.note_count == plan.syllable_count()


@pytest.mark.parametrize("case_name", GOLDEN_CASES)
def test_mock_stem_respects_plan_timing(tmp_path: Path, case_name: str):
    plan = _load_vocal_plan_case(case_name)
    stem_path = tmp_path / f"{case_name}_mock_vocal.wav"
    MockSvsRenderer().render(plan, stem_path=stem_path)
    metrics = assert_vocal_stem_timing(plan, stem_path)
    assert metrics["syllable_median_rms"] > metrics["rest_max_rms"]
