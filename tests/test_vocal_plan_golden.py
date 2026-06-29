import json
from pathlib import Path

from app.generators.vocal_plan import (
    SectionDensityKnobs,
    build_vocal_plan,
    plan_debug_rows,
    vocal_plan_timing_for,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "vocal_plan"
SCALE = [0, 2, 4, 5, 7, 9, 11]
ROOT_HZ = 261.63


def _load_case(name: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _avg_duration(plan_payload: dict, section_name: str) -> float:
    durations = [
        float(syl["beat_duration"])
        for section in plan_payload["sections"]
        if section["name"] == section_name
        for line in section["lines"]
        for syl in line["syllables"]
    ]
    return sum(durations) / max(len(durations), 1)


def _rebuild_case(name: str) -> dict:
    cases = json.loads((FIXTURE_DIR / "cases.json").read_text(encoding="utf-8"))
    case = cases[name]
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
    payload = plan.model_dump()
    payload["debug"] = plan_debug_rows(plan)
    return payload


def test_golden_pop_chorus_matches_fixture():
    golden = _load_case("pop_chorus")
    rebuilt = _rebuild_case("pop_chorus")
    assert rebuilt["version"] == 1
    assert rebuilt["sections"] == golden["sections"]
    assert rebuilt["timing"] == golden["timing"]
    assert rebuilt["debug"] == golden["debug"]


def test_golden_rap_dense_matches_fixture():
    golden = _load_case("rap_dense")
    rebuilt = _rebuild_case("rap_dense")
    assert rebuilt["debug"] == golden["debug"]
    rap_timing = rebuilt["timing"]
    assert rap_timing["line_rest_beats"] < 0.2
    assert rebuilt["section_density"]["verse"] == SectionDensityKnobs().rap_verse


def test_golden_ballad_held_matches_fixture():
    golden = _load_case("ballad_held")
    rebuilt = _rebuild_case("ballad_held")
    assert rebuilt["debug"] == golden["debug"]
    assert rebuilt["timing"]["phrase_end_hold"] >= 1.8


def test_pop_chorus_tighter_than_verse():
    plan = _rebuild_case("pop_chorus")
    assert _avg_duration(plan, "chorus") < _avg_duration(plan, "verse")


def test_ballad_phrase_end_longer_than_interior():
    plan = _rebuild_case("ballad_held")
    line = plan["sections"][0]["lines"][0]
    interiors = [s["beat_duration"] for s in line["syllables"] if not s["phrase_end"]]
    endings = [s["beat_duration"] for s in line["syllables"] if s["phrase_end"]]
    assert endings
    assert max(interiors or [0]) < endings[0]


def test_line_rests_present_between_lines():
    plan = _rebuild_case("pop_chorus")
    rests = [line["rest_beats_after"] for section in plan["sections"] for line in section["lines"]]
    assert any(rest >= 0.25 for rest in rests)
