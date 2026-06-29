from __future__ import annotations

import json
from pathlib import Path

from app.generators.svs.models import SvsNoteEvent, SvsRestEvent, SvsScore

_VOWEL_PHONES: frozenset[str] = frozenset({
    "AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY",
    "IH", "IY", "OW", "OY", "UH", "UW",
})
_MIN_CONSONANT_SEC: float = 0.06
_MIN_PHONE_SEC: float = 0.03


def _distribute_phone_durations(phonemes: list[str], note_sec: float) -> list[float]:
    """Consonants get _MIN_CONSONANT_SEC each; vowels share the rest."""
    if len(phonemes) == 1:
        return [max(note_sec, _MIN_PHONE_SEC)]

    n_consonants = sum(1 for p in phonemes if p not in _VOWEL_PHONES)
    n_vowels = len(phonemes) - n_consonants
    vowel_budget = max(note_sec - n_consonants * _MIN_CONSONANT_SEC, n_vowels * _MIN_PHONE_SEC)
    vowel_each = vowel_budget / max(n_vowels, 1)

    durs: list[float] = []
    for phone in phonemes:
        durs.append(round(vowel_each if phone in _VOWEL_PHONES else _MIN_CONSONANT_SEC, 4))

    # Adjust last entry so total duration == note_sec exactly.
    total = sum(durs)
    durs[-1] = max(round(durs[-1] + (note_sec - total), 4), _MIN_PHONE_SEC)
    return durs


def _phrase_to_segment(
    notes: list[SvsNoteEvent],
    seconds_per_beat: float,
    offset_sec: float,
) -> dict:
    ph_seq: list[str] = []
    ph_dur: list[str] = []
    ph_num: list[str] = []
    note_seq: list[str] = []
    note_dur: list[str] = []
    note_slur: list[str] = []

    for note in notes:
        note_sec = round(note.duration_beats * seconds_per_beat, 4)
        phones = note.phonemes
        durs = _distribute_phone_durations(phones, note_sec)

        ph_seq.extend(phones)
        ph_dur.extend(f"{d:.4f}" for d in durs)
        ph_num.append(str(len(phones)))
        note_seq.append(note.note_name)
        note_dur.append(f"{note_sec:.4f}")
        note_slur.append("1" if note.slur_to_next else "0")

    return {
        "offset": round(offset_sec, 4),
        "ph_seq": " ".join(ph_seq),
        "ph_dur": " ".join(ph_dur),
        "ph_num": " ".join(ph_num),
        "note_seq": " ".join(note_seq),
        "note_dur": " ".join(note_dur),
        "note_slur": " ".join(note_slur),
    }


def score_to_ds(score: SvsScore) -> list[dict]:
    """Translate SvsScore to DiffSinger .ds segment list.

    Rests become single SP phoneme segments; note phrases are grouped by
    phrase_end markers and separated by explicit SvsRestEvents.
    """
    spb = 60.0 / score.bpm
    segments: list[dict] = []
    current_notes: list[SvsNoteEvent] = []
    current_offset: float | None = None

    def _flush() -> None:
        nonlocal current_notes, current_offset
        if current_notes and current_offset is not None:
            segments.append(_phrase_to_segment(current_notes, spb, current_offset))
        current_notes.clear()
        current_offset = None

    for event in score.events:
        start_sec = round(event.start_beats * spb, 4)
        if isinstance(event, SvsRestEvent):
            _flush()
            dur_sec = round(event.duration_beats * spb, 4)
            segments.append({
                "offset": start_sec,
                "ph_seq": "SP",
                "ph_dur": f"{dur_sec:.4f}",
                "ph_num": "1",
                "note_seq": "rest",
                "note_dur": f"{dur_sec:.4f}",
                "note_slur": "0",
            })
        else:
            if current_offset is None:
                current_offset = start_sec
            current_notes.append(event)
            if event.phrase_end:
                _flush()

    _flush()
    return segments


def save_ds_file(score: SvsScore, path: Path) -> None:
    """Write DiffSinger .ds JSON to path."""
    segments = score_to_ds(score)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(segments, indent=2), encoding="utf-8")
