from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from app.core.ace_runtime import AceRuntimeStatus, load_runtime_profile
from app.core.audio_validation import validate_wav_output
from app.core.config import Settings
from app.core.hardware import AceGenConfig
from app.domain.models import GenerationRequest, GenerationResult, GeneratorInfo
from app.generators.ace_step.checkpoints import resolve_generation_plan
from app.generators.ace_step.command_builder import AceCommandBuilder
from app.generators.ace_step.env import ace_subprocess_env
from app.generators.ace_step.health import get_ace_status
from app.generators.ace_step.lora_meta import lora_meta_from_sources
from app.generators.procedural import ProceduralGenerator

logger = logging.getLogger(__name__)

_QUALITY_STEPS = {"draft": 8, "balanced": 24, "high": 50}


def _load_safe_config(settings: Settings) -> AceGenConfig | None:
    """Load persisted safe recommended config from data/ace_hardware_profile.json."""
    raw = load_runtime_profile(settings.data_dir)
    if not raw:
        return None
    try:
        status = AceRuntimeStatus.model_validate(raw)
        hw = status.hardware
        if hw and hw.safe_recommended_config:
            return hw.safe_recommended_config
    except Exception:
        pass
    return None


def _build_runtime_config_record(
    request: GenerationRequest,
    *,
    checkpoint: str,
    inference_steps: int,
    batch_size: int,
    offload_to_cpu: bool,
    profile_detected_at: str,
    is_turbo: bool,
    safe_cfg: AceGenConfig | None,
) -> dict[str, Any]:
    """Build the ace_runtime_config dict that gets stored on the song."""
    return {
        "checkpoint": checkpoint,
        "lm_model": "none",
        "use_lm": False,
        "inference_steps": inference_steps,
        "turbo_max_steps": 8 if is_turbo else None,
        "batch_size": batch_size,
        "offload_to_cpu": offload_to_cpu,
        "device": safe_cfg.device if safe_cfg else "cuda",
        "seed": request.seed,
        "duration_seconds": request.duration_seconds,
        "runtime_profile_detected_at": profile_detected_at,
        "config_tier": "quality_routed" if not is_turbo else ("safe_recommended" if safe_cfg else "fallback_defaults"),
    }


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
        lora_requested = bool(request.lora_path)
        if not status.can_generate:
            if lora_requested or not fallback_allowed:
                raise RuntimeError("ACE-Step is not ready and fallback is disabled: " + "; ".join(status.warnings))
            result = self.fallback.generate(request, output_path)
            result.generator_name = self.name
            result.metadata.update({
                "engine": "ace-step-command-v3.4",
                "backend": "procedural-fallback",
                "fallback_reason": "; ".join(status.warnings) or "ACE command is not ready",
            })
            return result

        # Load safe recommended config from persisted hardware profile
        safe_cfg = _load_safe_config(self.settings)
        profile_detected_at = ""
        raw = load_runtime_profile(self.settings.data_dir) or {}
        try:
            _status = AceRuntimeStatus.model_validate(raw)
            profile_detected_at = (_status.hardware.detected_at if _status.hardware else "")
            if not _status.ace_usable:
                raise RuntimeError("ACE runtime is not usable: " + (_status.user_message or "Unknown reason"))
        except RuntimeError:
            raise
        except Exception:
            pass
            
        # Safe tier LM breaks full-length generation (clips to ~10s headless). Keep LM off for songs.
        offload_to_cpu = safe_cfg.offload_to_cpu if safe_cfg is not None else True
        checkpoint, inference_steps, is_turbo = resolve_generation_plan(
            quality=request.quality,
            checkpoint_dir=self.settings.ace_model_dir.expanduser().resolve(),
        )
        batch_size = safe_cfg.batch_size if safe_cfg and safe_cfg.batch_size else 1

        cmd = self.builder.build(request, output_path)

        # Inject safe config args unless the template already includes them
        cmd_str = " ".join(cmd)
        if "--offload-to-cpu" not in cmd_str and offload_to_cpu:
            cmd.append("--offload-to-cpu")
        if "--use-lm" not in cmd_str:
            cmd += ["--use-lm", "false"]
        if "--config-path" not in cmd_str and checkpoint:
            cmd += ["--config-path", checkpoint]
        if "--inference-steps" not in cmd_str and "--steps" not in cmd_str:
            cmd += ["--inference-steps", str(inference_steps)]
        if "--batch-size" not in cmd_str:
            cmd += ["--batch-size", str(batch_size)]

        logger.info(
            "ace_command_start output=%s checkpoint=%s steps=%s offload=%s lm=off cmd=%s",
            output_path, checkpoint, inference_steps, offload_to_cpu, " ".join(cmd),
        )
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
            raise

        elapsed_seconds = round(time.monotonic() - started, 3)
        stdout_tail = completed.stdout[-4000:]
        stderr_tail = completed.stderr[-4000:]
        lora_meta = lora_meta_from_sources(
            output_path=output_path,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        if completed.returncode != 0:
            message = stderr_tail.strip() or stdout_tail.strip() or f"ACE-Step exited with {completed.returncode}"
            if fallback_allowed and not lora_requested:
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
        command_preview = " ".join(cmd)
        if len(command_preview) > 480:
            command_preview = command_preview[:477] + "..."

        runtime_config = _build_runtime_config_record(
            request,
            checkpoint=checkpoint,
            inference_steps=inference_steps,
            batch_size=batch_size,
            offload_to_cpu=offload_to_cpu,
            profile_detected_at=profile_detected_at,
            is_turbo=is_turbo,
            safe_cfg=safe_cfg,
        )

        result_metadata: dict[str, object] = {
            "engine": "ace-step-command-v3.4",
            "backend": "external-command",
            "device": self.settings.ace_device,
            "model_dir": str(self.settings.ace_model_dir),
            "hf_cache_dir": str(self.settings.hf_cache_dir) if self.settings.hf_cache_dir else None,
            "lora_path": request.lora_path,
            "lora_scale": request.lora_scale if request.lora_path else None,
            "use_lora": bool(request.lora_path),
            "command_preview": command_preview,
            "ace_returncode": completed.returncode,
            "ace_elapsed_seconds": elapsed_seconds,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "ace_runtime_config": runtime_config,
            "audio": {
                "file_size_bytes": audio.file_size_bytes,
                "duration_seconds": audio.duration_seconds,
                "sample_rate": audio.sample_rate,
                "channels": audio.channels,
                "peak_abs_sample": audio.peak_abs_sample,
                "rms": audio.rms,
                "warnings": audio.warnings,
            },
        }
        if lora_meta:
            result_metadata.update(lora_meta)
        elif request.lora_path:
            result_metadata.update({
                "loraLoadAttempted": True,
                "loraLoadSucceeded": False,
                "loraLoadMessage": "LoRA metadata sidecar missing",
                "loraPath": request.lora_path,
                "loraScale": request.lora_scale,
            })
        return GenerationResult(
            file_name=output_path.name,
            duration_seconds=round(audio.duration_seconds),
            sample_rate=audio.sample_rate,
            generator_name=self.name,
            metadata=result_metadata,
        )
