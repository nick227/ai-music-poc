from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from pathlib import Path

from app.core.audio_validation import validate_wav_output
from app.core.config import Settings
from app.domain.models import GenerationRequest, GenerationResult, GeneratorInfo
from app.generators.procedural import ProceduralGenerator
from app.generators.svs.command_builder import SvsCommandBuilder
from app.generators.svs.health import get_svs_status
from app.generators.svs.mock_audio import SAMPLE_RATE
from app.generators.svs.plan_export import save_svs_score, vocal_plan_to_score
from app.generators.svs.vocal_renderer import MockSvsRenderer
from app.generators.vocal_plan import build_vocal_plan, save_vocal_plan, vocal_plan_timing_for

logger = logging.getLogger(__name__)

MELODIC_CONTOURS = {
    "verse": [0, 1, 2, 1, 3, 2, 1, 0],
    "chorus": [2, 3, 4, 3, 4, 5, 4, 3],
    "build": [0, 2, 3, 4, 5, 4, 5, 6],
    "hook": [4, 3, 2, 1, 2, 3, 4, 3],
    "intro": [0, 1, 0, 1, 2, 1, 0, 1],
    "bridge": [0, 2, 1, 3, 2, 1, 0, 1],
    "breakdown": [0, 0, 1, 0, 0, 1, 0, 0],
    "outro": [3, 2, 1, 0, 1, 0, 0, 0],
}


class SvsCommandGenerator:
    name = "svs-vocal"
    label = "SVS Vocal (controlled plan)"
    supports_lyrics = True
    supports_seed = False
    supports_duration = True
    description = "Renders a vocal stem from VocalPlan via scripts/svs_runner.py; mock backend by default."

    def __init__(self, settings: Settings, fallback: ProceduralGenerator | None = None) -> None:
        self.settings = settings
        self.builder = SvsCommandBuilder(settings)
        self.fallback = fallback or ProceduralGenerator()

    def info(self) -> GeneratorInfo:
        status = get_svs_status(self.settings)
        can_generate = bool(status["can_generate"])
        allow_fallback = self.settings.svs_allow_fallback
        if can_generate:
            state = "ready"
            hint = None
        elif allow_fallback:
            state = "fallback-ready"
            hint = "SVS runner will use mock stems until an external backend is configured."
        else:
            state = "not-configured"
            hint = "; ".join(status["warnings"]) or "Enable SVS_ENABLED and configure SVS_SCRIPT."
        return GeneratorInfo(
            name=self.name,
            label=self.label,
            supports_lyrics=True,
            supports_seed=False,
            supports_duration=True,
            description=self.description,
            backend_type="adapter",
            available=can_generate or allow_fallback,
            status=state,
            install_hint=hint,
        )

    def _build_plan(self, request: GenerationRequest) -> object:
        if not request.lyrics.strip():
            raise ValueError("svs-vocal requires lyrics")
        procedural = self.fallback
        positive_text = f"{request.prompt} {request.lyrics} {request.mode} {request.structure}".lower()
        negative_text = request.negative_prompt.lower()
        profile = procedural._profile(positive_text, request.mode, negative_text)
        bpm = request.bpm or procedural._infer_bpm(positive_text, request.mode, profile)
        beat = 60.0 / bpm
        root = procedural._root_freq(request.key, request.prompt)
        return build_vocal_plan(
            request.lyrics,
            bpm=bpm,
            key=request.key,
            duration_beats=request.duration_seconds / beat,
            scale=profile.scale,
            root_hz=root,
            profile_name=profile.name,
            melodic_contours=MELODIC_CONTOURS,
            timing=vocal_plan_timing_for(profile.name, request.vocal_style),
        )

    def generate(self, request: GenerationRequest, output_path: Path) -> GenerationResult:
        if request.mode not in ("song", "vocal_demo"):
            raise ValueError("svs-vocal supports song and vocal_demo modes only")

        status = get_svs_status(self.settings)
        allow_fallback = request.allow_fallback and self.settings.svs_allow_fallback
        plan = self._build_plan(request)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        plan_path = output_path.with_name(f"{output_path.stem}_vocal_plan.json")
        score_path = output_path.with_name(f"{output_path.stem}_svs_score.json")
        stem_path = output_path.with_name(f"{output_path.stem}_vocal_stem.wav")
        report_path = output_path.with_name(f"{output_path.stem}_svs_report.json")
        save_vocal_plan(plan, plan_path)
        score = vocal_plan_to_score(plan)
        save_svs_score(score, score_path)

        metadata: dict[str, object] = {
            "engine": "svs-vocal-v1",
            "vocal_backend": "svs-command",
            "vocal_plan_file": plan_path.name,
            "svs_score_file": score_path.name,
            "vocal_stem_file": stem_path.name,
            "svs_score_version": score.version,
            "syllable_events": plan.syllable_count(),
        }

        if not status["can_generate"]:
            if not allow_fallback:
                raise RuntimeError("SVS is not ready and fallback is disabled: " + "; ".join(status["warnings"]))
            mock = MockSvsRenderer().render(plan, stem_path=stem_path, score_path=score_path)
            shutil.copy(stem_path, output_path)
            metadata.update({
                "vocal_backend": "svs-mock-fallback",
                "fallback_reason": "; ".join(status["warnings"]) or "SVS not configured",
                "svs_elapsed_seconds": mock.elapsed_seconds,
            })
            audio = validate_wav_output(output_path, expected_duration_seconds=request.duration_seconds)
            return GenerationResult(
                file_name=output_path.name,
                duration_seconds=round(audio.duration_seconds),
                sample_rate=audio.sample_rate,
                generator_name=self.name,
                metadata=metadata,
            )

        cmd = self.builder.build(score_path=score_path, output_path=stem_path, report_path=report_path)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                cmd,
                cwd=Path.cwd(),
                text=True,
                capture_output=True,
                timeout=self.settings.svs_timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            if not allow_fallback:
                raise RuntimeError(f"SVS runner timed out after {self.settings.svs_timeout_seconds}s") from exc
            mock = MockSvsRenderer().render(plan, stem_path=stem_path, score_path=score_path)
            shutil.copy(stem_path, output_path)
            metadata.update({
                "vocal_backend": "svs-mock-fallback",
                "fallback_reason": "SVS runner timed out",
                "svs_elapsed_seconds": mock.elapsed_seconds,
            })
            audio = validate_wav_output(output_path, expected_duration_seconds=request.duration_seconds)
            return GenerationResult(
                file_name=output_path.name,
                duration_seconds=round(audio.duration_seconds),
                sample_rate=audio.sample_rate,
                generator_name=self.name,
                metadata=metadata,
            )

        elapsed = round(time.monotonic() - started, 3)
        stdout_tail = completed.stdout[-4000:]
        stderr_tail = completed.stderr[-4000:]
        metadata.update({
            "svs_elapsed_seconds": elapsed,
            "svs_returncode": completed.returncode,
            "svs_stdout_tail": stdout_tail,
            "svs_stderr_tail": stderr_tail,
            "command_preview": " ".join(cmd)[:480],
        })

        svs_report: dict = {}
        if report_path.exists():
            try:
                svs_report = json.loads(report_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        metadata["svs_backend_type"] = self.settings.svs_backend
        if svs_report:
            metadata["svs_report_file"] = report_path.name
            if svs_report.get("tiger_dir"):
                metadata["svs_tiger_dir"] = svs_report["tiger_dir"]
            if svs_report.get("speaker"):
                metadata["svs_speaker"] = svs_report["speaker"]

        if completed.returncode != 0 or not stem_path.exists():
            message = stderr_tail.strip() or stdout_tail.strip() or f"SVS runner exited {completed.returncode}"
            if not allow_fallback:
                raise RuntimeError(message[:1600])
            mock = MockSvsRenderer().render(plan, stem_path=stem_path, score_path=score_path)
            shutil.copy(stem_path, output_path)
            metadata.update({
                "vocal_backend": "svs-mock-fallback",
                "fallback_reason": message[:1200],
            })
            audio = validate_wav_output(output_path, expected_duration_seconds=request.duration_seconds)
            return GenerationResult(
                file_name=output_path.name,
                duration_seconds=round(audio.duration_seconds),
                sample_rate=audio.sample_rate,
                generator_name=self.name,
                metadata=metadata,
            )

        shutil.copy(stem_path, output_path)
        audio = validate_wav_output(output_path, expected_duration_seconds=request.duration_seconds)
        metadata["audio"] = {
            "duration_seconds": audio.duration_seconds,
            "sample_rate": audio.sample_rate,
            "peak_abs_sample": audio.peak_abs_sample,
            "rms": audio.rms,
        }
        return GenerationResult(
            file_name=output_path.name,
            duration_seconds=round(audio.duration_seconds),
            sample_rate=audio.sample_rate or SAMPLE_RATE,
            generator_name=self.name,
            metadata=metadata,
        )
