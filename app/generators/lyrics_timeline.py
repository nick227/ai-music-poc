from __future__ import annotations

from dataclasses import dataclass

from app.generators.vocal_plan import VocalPlan, build_vocal_plan


@dataclass(frozen=True)
class LyricEvent:
    word: str
    beat_start: float
    beat_duration: float


_DEFAULT_SCALE = [0, 2, 4, 5, 7, 9, 11]


def build_lyric_timeline(lyrics: str, duration_beats: float) -> list[LyricEvent]:
    """Deprecated: prefer build_vocal_plan(). Returns syllable-level events."""
    plan = build_vocal_plan(
        lyrics,
        bpm=120,
        key=None,
        duration_beats=duration_beats,
        scale=_DEFAULT_SCALE,
        root_hz=261.63,
    )
    return [
        LyricEvent(word=syllable.text, beat_start=syllable.beat_start, beat_duration=syllable.beat_duration)
        for syllable in plan.flat_syllables()
    ]


def event_at(events: list[LyricEvent], beat_pos: float) -> LyricEvent | None:
    if not events:
        return None
    for event in events:
        end = event.beat_start + event.beat_duration
        if event.beat_start <= beat_pos < end:
            return event
    return None
