from __future__ import annotations

from pathlib import Path

from app.domain.models import GenerationRequest, GenerationResult, GeneratorInfo
from app.generators.ace_step import AceStepCommandGenerator
from app.generators.procedural import ProceduralGenerator


class AutoRenderGenerator:
    name = "auto-render"
    label = "Auto Render: Draft Parametric / Final ACE"
    supports_lyrics = True
    supports_seed = True
    supports_duration = True
    description = "Routes draft previews to the parametric engine and balanced/high renders to ACE-Step."

    def __init__(self, procedural: ProceduralGenerator, ace: AceStepCommandGenerator) -> None:
        self.procedural = procedural
        self.ace = ace

    def info(self) -> GeneratorInfo:
        ace_info = self.ace.info()
        status = "ready" if ace_info.status == "ready" else "draft-ready"
        hint = None
        if ace_info.status != "ready":
            hint = "Draft works now. Fix ACE-Step setup to enable neural final renders."
        return GeneratorInfo(
            name=self.name,
            label=self.label,
            supports_lyrics=True,
            supports_seed=True,
            supports_duration=True,
            description=self.description,
            backend_type="adapter",
            available=True,
            status=status,
            install_hint=hint,
        )

    def generate(self, request: GenerationRequest, output_path: Path) -> GenerationResult:
        if request.quality == "draft":
            result = self.procedural.generate(request, output_path)
            result.generator_name = self.name
            result.metadata.update({
                "render_route": "draft-parametric",
                "render_backend": "procedural-v3",
            })
            return result

        result = self.ace.generate(request, output_path)
        result.generator_name = self.name
        result.metadata.update({
            "render_route": "final-neural",
            "render_backend": "ace-step-command",
            "requested_quality": request.quality,
        })
        return result
