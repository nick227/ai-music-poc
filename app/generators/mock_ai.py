from pathlib import Path

from app.domain.models import GenerationRequest, GenerationResult, GeneratorInfo
from app.generators.procedural import ProceduralGenerator


class MockAIGenerator:
    name = "mock-ai"
    label = "Mock AI Adapter"
    supports_lyrics = True
    supports_seed = True
    supports_duration = True
    description = "Development adapter that simulates a model backend while using Procedural V3 output."

    def __init__(self) -> None:
        self.fallback = ProceduralGenerator()

    def info(self) -> GeneratorInfo:
        return GeneratorInfo(name=self.name, label=self.label, supports_lyrics=True, supports_seed=True, supports_duration=True, description=self.description, backend_type="adapter", status="simulated")

    def generate(self, request: GenerationRequest, output_path: Path) -> GenerationResult:
        result = self.fallback.generate(request, output_path)
        result.generator_name = self.name
        result.metadata.update({"engine": "mock-ai-v3", "backend": "procedural-v3"})
        return result
