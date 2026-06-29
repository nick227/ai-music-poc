from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class SvsNoteEvent(BaseModel):
    type: Literal["note"] = "note"
    syllable_text: str
    phonemes: list[str] = Field(min_length=1)
    midi: int
    note_name: str
    start_beats: float
    duration_beats: float
    stressed: bool = False
    phrase_end: bool = False
    slur_to_next: bool = False


class SvsRestEvent(BaseModel):
    type: Literal["rest"] = "rest"
    start_beats: float
    duration_beats: float


SvsEvent = Annotated[Union[SvsNoteEvent, SvsRestEvent], Field(discriminator="type")]


class SvsScore(BaseModel):
    version: int = 1
    bpm: int
    language: str = "en"
    duration_beats: float
    events: list[SvsNoteEvent | SvsRestEvent] = Field(default_factory=list)

    def note_events(self) -> list[SvsNoteEvent]:
        return [event for event in self.events if event.type == "note"]

    def rest_events(self) -> list[SvsRestEvent]:
        return [event for event in self.events if event.type == "rest"]
