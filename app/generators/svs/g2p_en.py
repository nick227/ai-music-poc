from __future__ import annotations

import re

_VOWEL_RE = re.compile(r"[aeiouy]+")

_VOWEL_PHONEMES: dict[str, str] = {
    "a": "AE",
    "e": "EH",
    "i": "IH",
    "o": "AA",
    "u": "AH",
    "y": "IY",
}

_DIGRAPHS: tuple[tuple[str, str], ...] = (
    ("igh", "AY"),
    ("eigh", "EY"),
    ("ough", "AW"),
    ("augh", "AO"),
    ("tion", "SH"),
    ("sion", "ZH"),
    ("ai", "EY"),
    ("ay", "EY"),
    ("ea", "IY"),
    ("ee", "IY"),
    ("oa", "OW"),
    ("oo", "UW"),
    ("ou", "AW"),
    ("ow", "OW"),
    ("oi", "OY"),
    ("oy", "OY"),
    ("ar", "AA"),
    ("er", "ER"),
    ("ir", "ER"),
    ("or", "AO"),
    ("ur", "ER"),
)

_CONSONANT_PHONEMES: dict[str, str] = {
    "b": "B",
    "c": "K",
    "d": "D",
    "f": "F",
    "g": "G",
    "h": "HH",
    "j": "JH",
    "k": "K",
    "l": "L",
    "m": "M",
    "n": "N",
    "p": "P",
    "q": "K",
    "r": "R",
    "s": "S",
    "t": "T",
    "v": "V",
    "w": "W",
    "x": "K S",
    "y": "Y",
    "z": "Z",
}


def _vowel_token(chunk: str) -> str:
    lowered = chunk.lower()
    for pattern, phoneme in _DIGRAPHS:
        if pattern in lowered:
            return phoneme
    return _VOWEL_PHONEMES.get(lowered[0], "AH")


def _consonant_token(chunk: str) -> list[str]:
    lowered = chunk.lower()
    if not lowered:
        return []
    if lowered == "th":
        return ["TH"]
    if lowered == "ch":
        return ["CH"]
    if lowered == "sh":
        return ["SH"]
    if lowered == "ng":
        return ["NG"]
    tokens: list[str] = []
    for char in lowered:
        mapped = _CONSONANT_PHONEMES.get(char)
        if mapped:
            tokens.extend(mapped.split())
    return tokens or ["UNK"]


def syllable_to_phonemes(syllable: str) -> list[str]:
    text = syllable.strip().lower()
    if not text:
        return ["SIL"]

    vowel_match = _VOWEL_RE.search(text)
    if vowel_match is None:
        return _consonant_token(text)

    onset = text[: vowel_match.start()]
    nucleus = text[vowel_match.start() : vowel_match.end()]
    coda = text[vowel_match.end() :]

    phonemes: list[str] = []
    phonemes.extend(_consonant_token(onset))
    phonemes.append(_vowel_token(nucleus))
    phonemes.extend(_consonant_token(coda))
    return phonemes or ["UNK"]
