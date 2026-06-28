from __future__ import annotations

import json
import logging
import shlex
import subprocess
from pathlib import Path
from string import Template

from app.core.config import Settings
from app.core.config import Settings
from app.core.ace_runtime import load_runtime_profile, AceRuntimeStatus
from app.domain.models import GenerationRequest, GenerationResult, GeneratorInfo
from app.generators.procedural import ProceduralGenerator

logger = logging.getLogger(__name__)


class AceStepGenerator:
    """ACE-Step adapter foundation.

    This adapter intentionally does not vendor ACE-Step or download model weights. It can call an
    external command once the user installs ACE-Step locally. Until then, it can safely fall back to
    ProceduralGenerator so the product flow remains functional.
    """

    name = "ace-step-local"
    label = "ACE-Step Local Adapter"
    supports_lyrics = True
    supports_seed = True
    supports_duration = True
    description = "External ACE-Step command adapter with safe procedural fallback when not configured."

    def __init__(self, settings: Settings, fallback: ProceduralGenerator | None = None) -> None:
        self.settings = settings
        self.fallback = fallback or ProceduralGenerator()

    def info(self) -> GeneratorInfo:
        configured = bool(self.settings.ace_step_command_template.strip())
        if configured:
            status = "configured"
            hint = None
        elif self.settings.ace_step_allow_fallback:
            status = "fallback-ready"
            hint = "Set ACE_STEP_COMMAND_TEMPLATE to call your local ACE-Step runner."
        else:
            status = "not-configured"
            hint = "Install ACE-Step and set ACE_STEP_COMMAND_TEMPLATE, or enable fallback."
        return GeneratorInfo(
            name=self.name,
            label=self.label,
            supports_lyrics=self.supports_lyrics,
            supports_seed=self.supports_seed,
            supports_duration=self.supports_duration,
            description=self.description,
            backend_type="adapter",
            available=configured or self.settings.ace_step_allow_fallback,
            status=status,
            install_hint=hint,
        )

    def generate(self, request: GenerationRequest, output_path: Path) -> GenerationResult:
        configured = bool(self.settings.ace_step_command_template.strip())
        fallback_allowed = request.use_fallback and self.settings.ace_step_allow_fallback
        if not configured:
            if not fallback_allowed:
                raise RuntimeError("ACE-Step is not configured. Set ACE_STEP_COMMAND_TEMPLATE or enable fallback.")
            logger.warning("ace_step_not_configured fallback=procedural output=%s", output_path)
            result = self.fallback.generate(request, output_path)
            result.generator_name = self.name
            result.metadata.update({
                "engine": "ace-step-adapter-v2.0",
                "backend": "procedural-fallback",
                "fallback_reason": "ACE_STEP_COMMAND_TEMPLATE is not set",
            })
            return result

        tmp_dir = self.settings.tmp_dir / output_path.stem
        tmp_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = tmp_dir / "prompt.txt"
        lyrics_file = tmp_dir / "lyrics.txt"
        request_file = tmp_dir / "request.json"
        prompt_file.write_text(request.prompt, encoding="utf-8")
        lyrics_file.write_text(request.lyrics, encoding="utf-8")
        request_file.write_text(request.model_dump_json(indent=2), encoding="utf-8")

        cmd = self._render_command(request, output_path, prompt_file, lyrics_file, request_file)
        logger.info("ace_step_command job_output=%s cmd=%s", output_path, " ".join(cmd))
        completed = subprocess.run(
            cmd,
            cwd=Path.cwd(),
            text=True,
            capture_output=True,
            timeout=self.settings.ace_step_timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or f"ACE-Step exited with {completed.returncode}"
            raise RuntimeError(message[:1200])
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError("ACE-Step command completed but did not create the expected output WAV.")

        # Load runtime config to record exactly what ran
        ace_cfg_dict = {}
        profile_data = load_runtime_profile(self.settings.data_dir)
        if profile_data:
            try:
                status = AceRuntimeStatus.model_validate(profile_data)
                if status.hardware and status.hardware.safe_recommended_config:
                    ace_cfg_dict = status.hardware.safe_recommended_config.model_dump()
            except Exception:
                pass

        return GenerationResult(
            file_name=output_path.name,
            duration_seconds=request.duration_seconds,
            sample_rate=44_100,
            generator_name=self.name,
            metadata={
                "engine": "ace-step-adapter-v2.0",
                "backend": "external-command",
                "device": ace_cfg_dict.get("device") or self.settings.ace_step_device,
                "model_dir": str(self.settings.ace_step_model_dir),
                "stdout_tail": completed.stdout[-1000:],
                "ace_runtime_config": ace_cfg_dict,
            },
        )

    def _render_command(
        self,
        request: GenerationRequest,
        output_path: Path,
        prompt_file: Path,
        lyrics_file: Path,
        request_file: Path,
    ) -> list[str]:
        profile_data = load_runtime_profile(self.settings.data_dir)
        device = self.settings.ace_step_device
        lm_model = ""
        batch_size = 1
        inference_steps = 8
        if profile_data:
            try:
                status = AceRuntimeStatus.model_validate(profile_data)
                if status.hardware and status.hardware.safe_recommended_config:
                    cfg = status.hardware.safe_recommended_config
                    device = cfg.device
                    lm_model = cfg.lm_model
                    batch_size = cfg.batch_size
                    inference_steps = cfg.inference_steps
            except Exception:
                pass

        values = {
            "prompt": request.prompt,
            "lyrics": request.lyrics,
            "title": request.title,
            "duration_seconds": str(request.duration_seconds),
            "seed": "" if request.seed is None else str(request.seed),
            "bpm": "" if request.bpm is None else str(request.bpm),
            "key": request.key or "",
            "mode": request.mode,
            "structure": request.structure,
            "quality": request.quality,
            "guidance_scale": str(request.guidance_scale),
            "negative_prompt": request.negative_prompt,
            "output_path": str(output_path),
            "prompt_file": str(prompt_file),
            "lyrics_file": str(lyrics_file),
            "request_file": str(request_file),
            "model_dir": str(self.settings.ace_step_model_dir),
            "device": device,
            "lm_model": lm_model,
            "batch_size": str(batch_size),
            "inference_steps": str(inference_steps),
        }
        rendered = Template(self.settings.ace_step_command_template).safe_substitute(values)
        return shlex.split(rendered)
