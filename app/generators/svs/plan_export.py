from __future__ import annotations

from pathlib import Path

from app.generators.svs.g2p_en import syllable_to_phonemes
from app.generators.svs.models import SvsNoteEvent, SvsRestEvent, SvsScore
from app.generators.vocal_plan import VocalPlan

_NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_BEAT_ROUND = 3


def midi_to_note_name(midi: int) -> str:
    return f"{_NOTE_NAMES[midi % 12]}{(midi // 12) - 1}"


def _round_beats(value: float) -> float:
    return round(value, _BEAT_ROUND)


def vocal_plan_to_score(plan: VocalPlan) -> SvsScore:
    events: list[SvsNoteEvent | SvsRestEvent] = []
    for section in plan.sections:
        for line in section.lines:
            syllables = line.syllables
            for index, syllable in enumerate(syllables):
                next_syllable = syllables[index + 1] if index + 1 < len(syllables) else None
                slur_to_next = (
                    next_syllable is not None
                    and not syllable.phrase_end
                )
                events.append(
                    SvsNoteEvent(
                        syllable_text=syllable.text,
                        phonemes=syllable_to_phonemes(syllable.text),
                        midi=syllable.pitch_midi,
                        note_name=midi_to_note_name(syllable.pitch_midi),
                        start_beats=_round_beats(syllable.beat_start),
                        duration_beats=_round_beats(syllable.beat_duration),
                        stressed=syllable.stressed,
                        phrase_end=syllable.phrase_end,
                        slur_to_next=slur_to_next,
                    )
                )
            if line.rest_beats_after > 0 and syllables:
                last = syllables[-1]
                rest_start = last.beat_start + last.beat_duration
                events.append(
                    SvsRestEvent(
                        start_beats=_round_beats(rest_start),
                        duration_beats=_round_beats(line.rest_beats_after),
                    )
                )
    return SvsScore(
        version=1,
        bpm=plan.bpm,
        language="en",
        duration_beats=_round_beats(plan.duration_beats),
        events=events,
    )


def save_svs_score(score: SvsScore, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(score.model_dump_json(indent=2), encoding="utf-8")


def load_svs_score(path: Path) -> SvsScore:
    return SvsScore.model_validate_json(path.read_text(encoding="utf-8"))
