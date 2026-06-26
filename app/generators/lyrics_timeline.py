from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LyricEvent:
    word: str
    beat_start: float
    beat_duration: float


def _clean_word(raw: str) -> str:
    return raw.strip(".,!?;:()[]{}\"'")


def build_lyric_timeline(lyrics: str, duration_beats: float) -> list[LyricEvent]:
    lines = [line.strip() for line in lyrics.splitlines() if line.strip()]
    if not lines:
        words = [_clean_word(w) for w in lyrics.split() if _clean_word(w)]
        if not words:
            return []
        lines = [" ".join(words)]

    events: list[LyricEvent] = []
    beat_cursor = 0.0
    beats_per_line = max(4.0, duration_beats / max(len(lines), 1))

    for line in lines:
        words = [_clean_word(w) for w in line.split() if _clean_word(w)]
        if not words:
            beat_cursor += beats_per_line * 0.5
            continue
        word_beats = beats_per_line / len(words)
        for word in words:
            events.append(LyricEvent(word=word, beat_start=beat_cursor, beat_duration=word_beats))
            beat_cursor += word_beats
        beat_cursor += word_beats * 0.35

    return events


def event_at(events: list[LyricEvent], beat_pos: float) -> LyricEvent | None:
    if not events:
        return None
    scaled = beat_pos
    for event in events:
        end = event.beat_start + event.beat_duration
        if event.beat_start <= scaled < end:
            return event
    return events[int(scaled) % len(events)]
