from __future__ import annotations

from pathlib import Path


def assert_wav_created(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError("Expected generated WAV was not created.")
