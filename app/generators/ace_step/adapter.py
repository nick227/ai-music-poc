from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from app.core.audio_validation import validate_wav_output
from app.core.config import Settings
from app.domain.models import GenerationRequest, GenerationResult, GeneratorInfo
from app.generators.ace_step.command_builder import AceCommandBuilder
from app.generators.ace_step.env import ace_subprocess_env
from app.generators.ace_step.health import get_ace_status
from app.generators.procedural import ProceduralGenerator

logger = logging.getLogger(__name__)


class AceStepCommandGenerator:
    name = "ace-step-command"
    label = "ACE-Step Command Adapter"
    supports_lyrics = True
    supports_seed = True
    supports_duration = True
    description = "Calls a user-installed ACE-Step runner through ACE_COMMAND_TEMPLATE; falls back only when allowed."

    def __init__(self, settings: Settings, fallback: ProceduralGenerator | None = None) -> None:
        self.settings = settings
        self.builder = AceCommandBuilder(settings)
        self.fallback = fallback or ProceduralGenerator()

    def info(self) -> GeneratorInfo:
        status = get_ace_status(self.settings)
        if status.can_generate:
            state = "ready"
            hint = None
        elif status.fallback_enabled:
            state = "fallback-ready"
            hint = "Install ACE-Step and set ACE_* values to use real model generation."
        else:
            state = "not-configured"
            hint = "; ".join(status.warnings) or "ACE is not configured."
        return GeneratorInfo(
            name=self.name,
            label=self.label,
            supports_lyrics=True,
            supports_seed=True,
            supports_duration=True,
            description=self.description,
            backend_type="adapter",
            available=status.can_generate or status.fallback_enabled,
            status=state,
            install_hint=hint,
        )

    def generate(self, request: GenerationRequest, output_path: Path) -> GenerationResult:
        status = get_ace_status(self.settings)
        fallback_allowed = request.allow_fallback and self.settings.ace_allow_fallback
        if not status.can_generate:
            if not fallback_allowed:
                raise RuntimeError("ACE-Step is not ready and fallback is disabled: " + "; ".join(status.warnings))
            result = self.fallback.generate(request, output_path)
            result.generator_name = self.name
            result.metadata.update({
                "engine": "ace-step-command-v3.4",
                "backend": "procedural-fallback",
                "fallback_reason": "; ".join(status.warnings) or "ACE command is not ready",
            })
            return result

        cmd = self.builder.build(request, output_path)
        logger.info("ace_command_start output=%s cmd=%s", output_path, " ".join(cmd))
        started = time.monotonic()
        try:
            completed = subprocess.run(
                cmd,
                cwd=Path.cwd(),
                text=True,
                capture_output=True,
                timeout=self.settings.ace_timeout_seconds,
                check=False,
                env=ace_subprocess_env(self.settings),
            )
        except subprocess.TimeoutExpired:
            # Let GenerationService mark TIMEOUT and write the job log.
            raise

        elapsed_seconds = round(time.monotonic() - started, 3)
        stdout_tail = completed.stdout[-4000:]
        stderr_tail = completed.stderr[-4000:]
        if completed.returncode != 0:
            message = stderr_tail.strip() or stdout_tail.strip() or f"ACE-Step exited with {completed.returncode}"
            if fallback_allowed:
                result = self.fallback.generate(request, output_path)
                result.generator_name = self.name
                result.metadata.update({
                    "engine": "ace-step-command-v3.4",
                    "backend": "procedural-fallback",
                    "fallback_reason": message[:1200],
                    "ace_returncode": completed.returncode,
                    "ace_elapsed_seconds": elapsed_seconds,
                    "ace_stdout_tail": stdout_tail,
                    "ace_stderr_tail": stderr_tail,
                })
                return result
            raise RuntimeError(message[:1600])

        audio = validate_wav_output(output_path, expected_duration_seconds=request.duration_seconds)
        return GenerationResult(
            file_name=output_path.name,
            duration_seconds=round(audio.duration_seconds),
            sample_rate=audio.sample_rate,
            generator_name=self.name,
            metadata={
                "engine": "ace-step-command-v3.4",
                "backend": "external-command",
                "device": self.settings.ace_device,
                "model_dir": str(self.settings.ace_model_dir),
                "hf_cache_dir": str(self.settings.hf_cache_dir) if self.settings.hf_cache_dir else None,
                "command": cmd,
                "ace_returncode": completed.returncode,
                "ace_elapsed_seconds": elapsed_seconds,
                "stdout_tail": stdout_tail,
                "stderr_tail": stderr_tail,
                "audio": {
                    "file_size_bytes": audio.file_size_bytes,
                    "duration_seconds": audio.duration_seconds,
                    "sample_rate": audio.sample_rate,
                    "channels": audio.channels,
                    "peak_abs_sample": audio.peak_abs_sample,
                    "rms": audio.rms,
                    "warnings": audio.warnings,
                },
            },
        )
