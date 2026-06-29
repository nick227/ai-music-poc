#!/usr/bin/env python3
"""Render a mock SVS vocal stem from lyrics or an existing vocal_plan.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.generators.svs import GOLDEN_CASE_NAMES, MockSvsRenderer, vocal_plan_to_score
from app.generators.vocal_plan import build_vocal_plan, load_vocal_plan, vocal_plan_timing_for

SCALE = [0, 2, 4, 5, 7, 9, 11]
ROOT_HZ = 261.63
CASES_PATH = REPO_ROOT / "tests" / "fixtures" / "vocal_plan" / "cases.json"


def _plan_from_case(name: str) -> object:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    case = cases[name]
    return build_vocal_plan(
        case["lyrics"],
        bpm=case["bpm"],
        key=case["key"],
        duration_beats=case["duration_beats"],
        scale=SCALE,
        root_hz=ROOT_HZ,
        profile_name=case["profile_name"],
        timing=vocal_plan_timing_for(case["profile_name"], case.get("vocal_style")),
    )


def _render_plan(plan: object, output_dir: Path, stem_name: str) -> None:
    stem_path = output_dir / stem_name
    result = MockSvsRenderer().render(plan, stem_path=stem_path)
    print(f"score: {result.score_path}")
    print(f"stem:  {result.stem_path}")
    print(f"notes: {result.note_count} rests: {result.rest_count} backend: {result.backend}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=GOLDEN_CASE_NAMES, default="pop_chorus")
    parser.add_argument("--plan", type=Path, help="Existing vocal_plan.json (overrides --case)")
    parser.add_argument(
        "--all-golden-cases",
        action="store_true",
        help="Render all golden vocal-plan fixtures (pop_chorus, rap_dense, ballad_held)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/experiments/svs-mock-v01"),
    )
    args = parser.parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.all_golden_cases:
        for case_name in GOLDEN_CASE_NAMES:
            plan = _plan_from_case(case_name)
            _render_plan(plan, output_dir, f"{case_name}_mock_vocal.wav")
        return

    if args.plan:
        plan = load_vocal_plan(args.plan.expanduser().resolve())
        stem_name = args.plan.stem.replace("_vocal_plan", "") + "_mock_vocal.wav"
    else:
        plan = _plan_from_case(args.case)
        stem_name = f"{args.case}_mock_vocal.wav"

    _render_plan(plan, output_dir, stem_name)
    preview = vocal_plan_to_score(plan).model_dump()
    print(f"first event: {preview['events'][0]}")


if __name__ == "__main__":
    main()
