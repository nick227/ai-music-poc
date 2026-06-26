from __future__ import annotations

import re

SECTION_MARKERS = ("verse", "chorus", "bridge", "hook", "intro", "outro", "pre-chorus", "pre chorus")
MAX_WORDS_PER_LINE = 8


def _normalize_section_label(raw: str) -> str:
    label = raw.strip().rstrip(":").strip().lower()
    return label.title()


def _wrap_line(words: list[str], max_words: int = MAX_WORDS_PER_LINE) -> list[str]:
    if not words:
        return []
    lines: list[str] = []
    for i in range(0, len(words), max_words):
        lines.append(" ".join(words[i : i + max_words]))
    return lines


def format_lyrics(text: str, structure: str = "verse_chorus") -> str:
    cleaned = text.strip()
    if not cleaned:
        return ""

    sections: list[tuple[str, list[str]]] = []
    current_label = "Verse"
    current_words: list[str] = []

    marker_pattern = re.compile(r"^\s*(verse|chorus|bridge|hook|intro|outro|pre[- ]?chorus)\s*:?\s*(.*)$", re.I)
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            if current_words:
                sections.append((current_label, current_words))
                current_words = []
            continue
        match = marker_pattern.match(line)
        if match:
            if current_words:
                sections.append((current_label, current_words))
                current_words = []
            current_label = _normalize_section_label(match.group(1))
            remainder = match.group(2).strip()
            if remainder:
                current_words.extend(remainder.split())
            continue
        current_words.extend(line.split())

    if current_words:
        sections.append((current_label, current_words))

    if not sections:
        sections = [("Verse", cleaned.split())]

    if structure == "verse_chorus" and len(sections) == 1:
        words = sections[0][1]
        midpoint = max(1, len(words) // 2)
        sections = [
            ("Verse", words[:midpoint]),
            ("Chorus", words[midpoint:]),
        ]

    output: list[str] = []
    for label, words in sections:
        output.append(f"{label}:")
        output.extend(_wrap_line(words))
        output.append("")

    return "\n".join(output).strip() + "\n"
