from __future__ import annotations

PROGRESSIONS: dict[str, list[int]] = {
    "pop": [0, 4, 5, 3],
    "disco": [0, 3, 5, 4],
    "club": [0, 5, 3, 4],
    "acoustic": [0, 5, 3, 4],
    "cinematic": [0, 3, 5, 2],
    "lofi": [0, 3, 4, 0],
    "ambient": [0, 2, 4, 5],
    "rap": [0, 0, 3, 4],
    "default": [0, 5, 3, 4],
}


def chord_step(profile_name: str, bar: int, section: str) -> int:
    steps = PROGRESSIONS.get(profile_name, PROGRESSIONS["default"])
    offset = 1 if section in ("chorus", "hook", "build") else 0
    return steps[(bar + offset) % len(steps)]
