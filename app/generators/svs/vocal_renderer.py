from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.generators.svs.mock_audio import render_score_to_wav
from app.generators.svs.plan_export import save_svs_score, vocal_plan_to_score
from app.generators.vocal_plan import VocalPlan


@dataclass(frozen=True)
class VocalRenderResult:
    stem_path: Path
    score_path: Path
    backend: str
    elapsed_seconds: float
    note_count: int
    rest_count: int


class VocalRenderer(Protocol):
    name: str

    def render(self, plan: VocalPlan, *, stem_path: Path, score_path: Path | None = None) -> VocalRenderResult:
        ...


class MockSvsRenderer:
    name = "svs-mock"

    def render(self, plan: VocalPlan, *, stem_path: Path, score_path: Path | None = None) -> VocalRenderResult:
        started = time.monotonic()
        score = vocal_plan_to_score(plan)
        resolved_score_path = score_path or stem_path.with_name(f"{stem_path.stem}_svs_score.json")
        save_svs_score(score, resolved_score_path)
        render_score_to_wav(score, stem_path)
        return VocalRenderResult(
            stem_path=stem_path,
            score_path=resolved_score_path,
            backend=self.name,
            elapsed_seconds=round(time.monotonic() - started, 3),
            note_count=len(score.note_events()),
            rest_count=len(score.rest_events()),
        )
