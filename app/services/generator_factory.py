from __future__ import annotations

from app.generators.base import MusicGenerator
from app.generators.procedural import ProceduralMusicGenerator


def create_generator() -> MusicGenerator:
    # Replace this with env-driven selection when adding real model adapters.
    return ProceduralMusicGenerator()
