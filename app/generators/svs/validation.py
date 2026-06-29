from __future__ import annotations

from app.generators.svs.models import SvsScore
from app.generators.svs.notes import midi_to_note_name

SVS_SCORE_VERSION = 1
_BEAT_EPSILON = 0.001


class SvsScoreValidationError(ValueError):
    pass


def validate_svs_score(score: SvsScore) -> None:
    if score.version != SVS_SCORE_VERSION:
        raise SvsScoreValidationError(f"unsupported svs_score version {score.version}; expected {SVS_SCORE_VERSION}")
    if score.bpm <= 0:
        raise SvsScoreValidationError("bpm must be positive")
    if score.duration_beats <= 0:
        raise SvsScoreValidationError("duration_beats must be positive")
    if score.language != "en":
        raise SvsScoreValidationError(f"unsupported language {score.language!r}")

    previous_start = -1.0
    for index, event in enumerate(score.events):
        if event.start_beats < previous_start - _BEAT_EPSILON:
            raise SvsScoreValidationError(f"events must be non-decreasing at index {index}")
        previous_start = event.start_beats

        if event.type == "note":
            if event.duration_beats <= 0:
                raise SvsScoreValidationError(f"note {event.syllable_text!r} has non-positive duration")
            end = event.start_beats + event.duration_beats
            if end > score.duration_beats + _BEAT_EPSILON:
                raise SvsScoreValidationError(f"note {event.syllable_text!r} exceeds duration_beats")
            expected_name = midi_to_note_name(event.midi)
            if event.note_name != expected_name:
                raise SvsScoreValidationError(
                    f"note {event.syllable_text!r} note_name {event.note_name!r} != midi {event.midi} ({expected_name})"
                )
            continue

        if event.duration_beats <= 0:
            raise SvsScoreValidationError("rest has non-positive duration")
        if event.start_beats + event.duration_beats > score.duration_beats + _BEAT_EPSILON:
            raise SvsScoreValidationError("rest exceeds duration_beats")
