from __future__ import annotations

from typing import Protocol

from app.core.config import Settings
from app.domain.models import GenerationRequest, GenerationResult, GeneratorInfo
from pathlib import Path


class Generator(Protocol):
    name: str
    def info(self) -> GeneratorInfo: ...
    def generate(self, request: GenerationRequest, output_path: Path) -> GenerationResult: ...


class GeneratorRegistry:
    def __init__(self) -> None:
        self._generators: dict[str, Generator] = {}

    def register(self, generator: Generator) -> None:
        self._generators[generator.name] = generator

    def get(self, name: str) -> Generator:
        return self._generators[name]

    def names(self) -> list[str]:
        return sorted(self._generators.keys())

    def list(self) -> list[GeneratorInfo]:
        return [self._generators[name].info() for name in self.names()]


def create_default_registry(settings: Settings) -> GeneratorRegistry:
    from app.generators.ace_step import AceStepCommandGenerator
    from app.generators.ace_cpp import AceCppGenerator
    from app.generators.auto_render import AutoRenderGenerator
    from app.generators.mock_ai import MockAIGenerator
    from app.generators.svs.adapter import SvsCommandGenerator
    from app.generators.procedural import ProceduralGenerator

    registry = GeneratorRegistry()
    procedural = ProceduralGenerator()
    ace = AceStepCommandGenerator(settings=settings, fallback=procedural)
    registry.register(AutoRenderGenerator(procedural=procedural, ace=ace))
    registry.register(procedural)
    registry.register(MockAIGenerator())
    registry.register(ace)
    registry.register(AceCppGenerator(timeout_seconds=settings.ace_timeout_seconds))
    registry.register(SvsCommandGenerator(settings=settings, fallback=procedural))
    return registry
