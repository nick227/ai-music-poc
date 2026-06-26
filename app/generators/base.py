from pathlib import Path
from typing import Protocol

from app.domain.models import GenerationRequest, GenerationResult, GeneratorInfo


class MusicGenerator(Protocol):
    name: str
    label: str
    supports_lyrics: bool
    supports_seed: bool
    supports_duration: bool
    description: str

    def info(self) -> GeneratorInfo:
        ...

    def generate(self, request: GenerationRequest, output_path: Path) -> GenerationResult:
        ...
