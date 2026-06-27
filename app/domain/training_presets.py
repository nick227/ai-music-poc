from __future__ import annotations

TRAINING_PRESETS: dict[str, dict[str, int | float | str]] = {
    "calibration": {
        "steps": 100,
        "rank": 8,
        "learning_rate": 1e-4,
        "epochs": 1,
    },
    "standard": {
        "steps": 500,
        "rank": 16,
        "learning_rate": 1e-4,
        "epochs": 3,
    },
}


def resolve_training_preset(name: str) -> dict[str, int | float | str]:
    preset = TRAINING_PRESETS.get(name)
    if preset is None:
        raise KeyError(name)
    return dict(preset)
