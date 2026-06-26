from __future__ import annotations

from dataclasses import dataclass

from app.domain.models import GenerationRequest


@dataclass(frozen=True)
class QualityProfile:
    harmonics: int
    reverb_mix: float
    vocal_reverb: float
    vocal_delay_mix: float
    drum_sub_layer: bool
    export_vocal_stem: bool
    mix_drive: float


QUALITY_PROFILES: dict[str, QualityProfile] = {
    "draft": QualityProfile(6, 0.06, 0.10, 0.04, False, False, 1.05),
    "balanced": QualityProfile(9, 0.12, 0.16, 0.07, True, True, 1.08),
    "high": QualityProfile(12, 0.18, 0.22, 0.10, True, True, 1.12),
}


def quality_for(request: GenerationRequest) -> QualityProfile:
    return QUALITY_PROFILES[request.quality]
