from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.domain.models import GenerationRequest, GenerationResult, GeneratorInfo

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 900


class AceCppGenerator:
    """ACE.cpp experimental sidecar backend."""

    name = "ace-cpp"
    label = "ACE.cpp (Experimental)"
    supports_lyrics = True
    supports_seed = True
    supports_duration = False
    description = "Experimental high-performance C++ backend using GGUF models."

    def __init__(self, timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS) -> None:
        self.repo_path = Path("/home/administrator/models/acestep.cpp")
        self.gguf_path = Path("/home/administrator/models/ace-gguf")
        self.binary_lm = self.repo_path / "build" / "ace-lm"
        self.binary_synth = self.repo_path / "build" / "ace-synth"
        self.timeout_seconds = timeout_seconds

    def info(self) -> GeneratorInfo:
        configured = self.binary_lm.exists() and self.binary_synth.exists()
        return GeneratorInfo(
            name=self.name,
            label=self.label,
            supports_lyrics=self.supports_lyrics,
            supports_seed=self.supports_seed,
            supports_duration=self.supports_duration,
            description=self.description,
            backend_type="local",
            available=configured,
            status="configured" if configured else "not-configured",
            install_hint=None if configured else "Build ACE.cpp and place GGUF models.",
        )

    def generate(self, request: GenerationRequest, output_path: Path) -> GenerationResult:
        if not (self.binary_lm.exists() and self.binary_synth.exists()):
            raise RuntimeError("ACE.cpp binaries not found.")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            req_json_path = temp_path / "request.json"

            request_data = {
                "caption": request.prompt,
                "output_format": "wav16" if output_path.suffix == ".wav" else "mp3",
            }
            if request.lyrics:
                request_data["lyrics"] = request.lyrics
            if request.seed is not None:
                request_data["seed"] = request.seed

            with open(req_json_path, "w") as f:
                json.dump(request_data, f)

            logger.info("Running ACE.cpp ace-lm")
            lm_cmd = [
                str(self.binary_lm),
                "--models", str(self.gguf_path),
                "--request", str(req_json_path),
            ]
            lm_result = subprocess.run(
                lm_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            if lm_result.returncode != 0:
                detail = (lm_result.stderr[-2000:] or lm_result.stdout[-2000:]).strip()
                raise RuntimeError(
                    f"ace-lm exited {lm_result.returncode}: {detail or '(no output)'}"
                )

            req0_json_path = temp_path / "request0.json"
            if not req0_json_path.exists():
                raise RuntimeError(
                    f"ace-lm did not produce expected {req0_json_path}"
                )

            logger.info("Running ACE.cpp ace-synth")
            synth_cmd = [
                str(self.binary_synth),
                "--models", str(self.gguf_path),
                "--request", str(req0_json_path),
            ]
            synth_result = subprocess.run(
                synth_cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            if synth_result.returncode != 0:
                detail = (synth_result.stderr[-2000:] or synth_result.stdout[-2000:]).strip()
                raise RuntimeError(
                    f"ace-synth exited {synth_result.returncode}: {detail or '(no output)'}"
                )

            output_format = request_data["output_format"]
            ext = "wav" if output_format.startswith("wav") else "mp3"
            generated_audio = temp_path / f"request00.{ext}"

            if not generated_audio.exists():
                raise RuntimeError(
                    f"ace-synth did not produce expected {generated_audio}"
                )

            shutil.copy(generated_audio, output_path)

        return GenerationResult(
            file_name=output_path.name,
            duration_seconds=request.duration_seconds,
            sample_rate=44_100,
            generator_name=self.name,
            metadata={
                "engine": "ace-cpp",
                "backend": "sidecar",
            },
        )
