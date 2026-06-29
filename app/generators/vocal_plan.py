from __future__ import annotations

import json
import math
import re
from pathlib import Path

from pydantic import BaseModel, Field

SECTION_MARKER = re.compile(
    r"^\s*(verse|chorus|bridge|hook|intro|outro|pre[- ]?chorus)\s*:?\s*(.*)$",
    re.IGNORECASE,
)
_VOWELS = frozenset("aeiouy")

DEFAULT_MELODIC_CONTOURS: dict[str, list[int]] = {
    "verse": [0, 1, 2, 1, 3, 2, 1, 0],
    "chorus": [2, 3, 4, 3, 4, 5, 4, 3],
    "build": [0, 2, 3, 4, 5, 4, 5, 6],
    "hook": [4, 3, 2, 1, 2, 3, 4, 3],
    "intro": [0, 1, 0, 1, 2, 1, 0, 1],
    "bridge": [0, 2, 1, 3, 2, 1, 0, 1],
    "breakdown": [0, 0, 1, 0, 0, 1, 0, 0],
    "outro": [3, 2, 1, 0, 1, 0, 0, 0],
}


class PlanSyllable(BaseModel):
    text: str
    beat_start: float
    beat_duration: float
    pitch_midi: int
    stressed: bool = False


class PlanLine(BaseModel):
    text: str
    syllables: list[PlanSyllable] = Field(default_factory=list)


class PlanSection(BaseModel):
    name: str
    beat_start: float
    beat_end: float
    lines: list[PlanLine] = Field(default_factory=list)


class VocalPlan(BaseModel):
    version: int = 0
    bpm: int
    key: str | None = None
    duration_beats: float
    sections: list[PlanSection] = Field(default_factory=list)

    def syllable_count(self) -> int:
        return sum(len(line.syllables) for section in self.sections for line in section.lines)

    def flat_syllables(self) -> list[PlanSyllable]:
        out: list[PlanSyllable] = []
        for section in self.sections:
            for line in section.lines:
                out.extend(line.syllables)
        return out


def _clean_word(raw: str) -> str:
    return raw.strip(".,!?;:()[]{}\"'")


def syllabify_word(word: str) -> list[tuple[str, bool]]:
    w = _clean_word(word).lower()
    if not w:
        return []
    chunks = re.findall(r"[^aeiouy]*[aeiouy]+(?:[^aeiouy](?![aeiouy]))?", w)
    if not chunks:
        chunks = [w]
    stressed = [index == 0 for index in range(len(chunks))]
    if len(chunks) > 1 and w.endswith(("tion", "sion", "cian")):
        stressed[-2] = True
        stressed[0] = False
    return list(zip(chunks, stressed))


def _parse_lyric_sections(lyrics: str) -> list[tuple[str, list[str]]]:
    lines_in = [line.strip() for line in lyrics.splitlines()]
    sections: list[tuple[str, list[str]]] = []
    label = "verse"
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if current:
            sections.append((label, current))
            current = []

    for raw in lines_in:
        if not raw:
            flush()
            continue
        match = SECTION_MARKER.match(raw)
        if match:
            flush()
            label = match.group(1).lower().replace(" ", "-").replace("pre-chorus", "pre-chorus")
            if label == "pre chorus":
                label = "pre-chorus"
            remainder = match.group(2).strip()
            if remainder:
                current.append(remainder)
            continue
        current.append(raw)

    flush()
    if not sections:
        words = [_clean_word(w) for w in lyrics.split() if _clean_word(w)]
        if words:
            sections.append(("verse", [" ".join(words)]))
    return sections


def _section_density(section_name: str, profile_name: str) -> float:
    name = section_name.lower()
    if profile_name == "rap":
        return 0.72 if name in ("chorus", "hook") else 0.85
    if name in ("chorus", "hook"):
        return 0.88
    if name == "bridge":
        return 1.08
    return 1.0


def _syllable_weight(stressed: bool, profile_name: str) -> float:
    base = 1.35 if stressed else 0.85
    if profile_name == "rap":
        return base * 0.78
    return base


def _hz_to_midi(hz: float) -> int:
    return int(round(12.0 * math.log2(max(hz, 1.0) / 440.0) + 69))


def _pitch_midi(
    global_index: int,
    section_name: str,
    scale: list[int],
    root_hz: float,
    contours: dict[str, list[int]],
) -> int:
    section_key = section_name.lower().replace("pre-chorus", "verse")
    contour = contours.get(section_key, contours["verse"])
    step = global_index % len(contour)
    degree = scale[(contour[step] + 2) % len(scale)]
    return _hz_to_midi(root_hz) + degree + 12


def build_vocal_plan(
    lyrics: str,
    *,
    bpm: int,
    key: str | None,
    duration_beats: float,
    scale: list[int],
    root_hz: float,
    profile_name: str = "default",
    melodic_contours: dict[str, list[int]] | None = None,
) -> VocalPlan:
    contours = melodic_contours or DEFAULT_MELODIC_CONTOURS
    parsed = _parse_lyric_sections(lyrics)
    if not parsed:
        return VocalPlan(bpm=bpm, key=key, duration_beats=duration_beats)

    structured: list[tuple[str, str, list[tuple[str, bool]]]] = []
    for section_name, line_texts in parsed:
        for line_text in line_texts:
            words = [_clean_word(w) for w in line_text.split() if _clean_word(w)]
            syllables: list[tuple[str, bool]] = []
            for word in words:
                syllables.extend(syllabify_word(word))
            if syllables:
                structured.append((section_name, line_text, syllables))

    if not structured:
        return VocalPlan(bpm=bpm, key=key, duration_beats=duration_beats)

    section_names = [item[0] for item in structured]
    section_weight_totals: dict[str, float] = {}
    for section_name, _, syllables in structured:
        density = _section_density(section_name, profile_name)
        weight = sum(_syllable_weight(stressed, profile_name) for _, stressed in syllables) * density
        section_weight_totals[section_name] = section_weight_totals.get(section_name, 0.0) + weight

    total_weight = sum(section_weight_totals.values()) or 1.0
    usable_beats = max(duration_beats * 0.92, 4.0)
    section_beat_budget = {
        name: usable_beats * (weight / total_weight)
        for name, weight in section_weight_totals.items()
    }

    cursor = 0.0
    global_index = 0
    plan_sections: list[PlanSection] = []
    current_section: PlanSection | None = None
    line_gap = 0.18 if profile_name != "rap" else 0.08

    for section_name, line_text, syllables in structured:
        if current_section is None or current_section.name != section_name:
            if current_section is not None:
                current_section.beat_end = max(current_section.beat_start + 0.01, cursor)
                plan_sections.append(current_section)
                cursor += line_gap
            current_section = PlanSection(name=section_name, beat_start=cursor, beat_end=cursor, lines=[])

        syllable_weights = [_syllable_weight(stressed, profile_name) for _, stressed in syllables]
        weight_sum = sum(syllable_weights) or 1.0
        section_budget = section_beat_budget[section_name]
        line_share = weight_sum * _section_density(section_name, profile_name)
        line_beats = section_budget * (line_share / max(section_weight_totals[section_name], 0.001))

        line_syllables: list[PlanSyllable] = []
        line_cursor = cursor
        for (text, stressed), weight in zip(syllables, syllable_weights):
            beat_duration = max(0.12, line_beats * (weight / weight_sum))
            beat_start = round(line_cursor * 4.0) / 4.0 if stressed else line_cursor
            line_syllables.append(
                PlanSyllable(
                    text=text,
                    beat_start=beat_start,
                    beat_duration=beat_duration,
                    pitch_midi=_pitch_midi(global_index, section_name, scale, root_hz, contours),
                    stressed=stressed,
                )
            )
            line_cursor += beat_duration
            global_index += 1

        current_section.lines.append(PlanLine(text=line_text, syllables=line_syllables))
        cursor = line_cursor

    if current_section is not None:
        current_section.beat_end = max(current_section.beat_start + 0.01, cursor)
        plan_sections.append(current_section)

    return VocalPlan(
        version=0,
        bpm=bpm,
        key=key,
        duration_beats=duration_beats,
        sections=plan_sections,
    )


def syllable_at(plan: VocalPlan, beat_pos: float) -> tuple[PlanSyllable, int] | None:
    flat = plan.flat_syllables()
    if not flat:
        return None
    for index, syllable in enumerate(flat):
        end = syllable.beat_start + syllable.beat_duration
        if syllable.beat_start <= beat_pos < end:
            return syllable, index
    return flat[int(beat_pos) % len(flat)], int(beat_pos) % len(flat)


def midi_to_hz(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0))


def save_vocal_plan(plan: VocalPlan, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")


def load_vocal_plan(path: Path) -> VocalPlan:
    return VocalPlan.model_validate_json(path.read_text(encoding="utf-8"))
