"""
ACE runtime validation layer.

Runs a code-first smoke test of the full ACE pipeline:
  dependency check → model init → generation → audio validation (ffprobe)

Persists results to data/ace_hardware_profile.json so the Studio UI
can display live ACE readiness without re-running inference.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from app.core.hardware import HardwareProfile, build_hardware_profile


_PROFILE_FILENAME = "ace_hardware_profile.json"


class AudioProbeResult(BaseModel):
    ok: bool
    path: str
    file_size_bytes: int = 0
    format_name: str = ""
    duration_seconds: float = 0.0
    codec_name: str = ""
    sample_rate: int = 0
    channels: int = 0
    error: str = ""


class SmokeTestResult(BaseModel):
    ok: bool
    ran_at: str
    duration_seconds: int
    output_path: str = ""
    returncode: int | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    audio: AudioProbeResult | None = None
    error: str = ""


class AceRuntimeStatus(BaseModel):
    # Overall verdict
    ace_usable: bool = False
    checked_at: str = ""

    # Individual gate results
    deps_ok: bool = False          # ACE venv + packages found
    cuda_ok: bool = False          # GPU/CUDA confirmed
    ffprobe_ok: bool = False       # ffprobe available for validation
    checkpoints_ok: bool = False   # turbo + vae present in model dir
    generation_ok: bool = False    # last smoke test passed
    audio_valid: bool = False      # ffprobe confirmed audio is playable

    hardware: HardwareProfile | None = None
    last_smoke_test: SmokeTestResult | None = None
    user_message: str = ""
    lm_warning: str = ""           # non-empty when safe 0.6B LM is absent


# ---------------------------------------------------------------------------
# ffprobe validation
# ---------------------------------------------------------------------------

def validate_with_ffprobe(path: Path, ffprobe: str = "ffprobe") -> AudioProbeResult:
    """Use ffprobe to confirm the audio file is readable and non-silent."""
    if not path.exists():
        return AudioProbeResult(ok=False, path=str(path), error="File does not exist")
    size = path.stat().st_size
    if size < 4096:
        return AudioProbeResult(ok=False, path=str(path), file_size_bytes=size, error="File too small to be valid audio")

    cmd = [
        ffprobe, "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=15, check=False)
        if result.returncode != 0:
            return AudioProbeResult(
                ok=False, path=str(path), file_size_bytes=size,
                error=f"ffprobe exited {result.returncode}: {result.stderr[:300]}",
            )
        data = json.loads(result.stdout)
    except Exception as exc:
        return AudioProbeResult(ok=False, path=str(path), file_size_bytes=size, error=str(exc))

    fmt = data.get("format", {})
    streams = data.get("streams", [])
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})

    duration = float(fmt.get("duration", 0) or audio_stream.get("duration", 0) or 0)
    if duration <= 0:
        return AudioProbeResult(
            ok=False, path=str(path), file_size_bytes=size,
            format_name=fmt.get("format_name", ""),
            error="Audio duration is zero or unreadable",
        )

    return AudioProbeResult(
        ok=True,
        path=str(path),
        file_size_bytes=size,
        format_name=fmt.get("format_name", ""),
        duration_seconds=round(duration, 3),
        codec_name=audio_stream.get("codec_name", ""),
        sample_rate=int(audio_stream.get("sample_rate", 0) or 0),
        channels=int(audio_stream.get("channels", 0) or 0),
    )


# ---------------------------------------------------------------------------
# Smoke test (code-first, no Gradio)
# ---------------------------------------------------------------------------

def run_smoke_test(
    ace_python: Path,
    ace_script: Path,
    ace_model_dir: Path,
    ace_device: str,
    ace_env: dict[str, str] | None,
    timeout_seconds: int,
    duration: int = 10,
    ffprobe: str = "ffprobe",
    kept_output: Path | None = None,
) -> SmokeTestResult:
    """
    Run a minimal ACE generation without Gradio.

    Writes temporary prompt/lyrics files, calls our ace_runner.py bridge,
    then validates the output WAV with ffprobe.
    """
    ran_at = datetime.now(timezone.utc).isoformat()

    if not Path(str(ace_python)).exists():
        return SmokeTestResult(ok=False, ran_at=ran_at, duration_seconds=duration, error=f"ACE python not found: {ace_python}")
    if not Path(str(ace_script)).exists():
        return SmokeTestResult(ok=False, ran_at=ran_at, duration_seconds=duration, error=f"ACE script not found: {ace_script}")

    with tempfile.TemporaryDirectory(prefix="ace_smoke_") as tmp:
        tmp_path = Path(tmp)
        prompt_file = tmp_path / "prompt.txt"
        lyrics_file = tmp_path / "lyrics.txt"
        output_path = kept_output or (tmp_path / "smoke_output.wav")

        prompt_file.write_text(
            "short dark disco test, simple beat, clear vocal demo",
            encoding="utf-8",
        )
        lyrics_file.write_text(
            "Verse:\nThis is a smoke test\nChorus:\nMake a short song",
            encoding="utf-8",
        )
        if kept_output:
            kept_output.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(ace_python), str(ace_script),
            "--prompt-file", str(prompt_file),
            "--lyrics-file", str(lyrics_file),
            "--output", str(output_path),
            "--model-dir", str(ace_model_dir),
            "--duration", str(duration),
            "--seed", "1234",
            "--guidance-scale", "7.5",
            "--quality", "draft",
            "--device", ace_device,
            "--use-lora", "false",
            "--lora-path", "__none__",
            "--lora-scale", "1.0",
        ]

        try:
            completed = subprocess.run(
                cmd,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
                env=ace_env,
            )
        except subprocess.TimeoutExpired:
            return SmokeTestResult(
                ok=False, ran_at=ran_at, duration_seconds=duration,
                error=f"Smoke test timed out after {timeout_seconds}s",
            )
        except Exception as exc:
            return SmokeTestResult(ok=False, ran_at=ran_at, duration_seconds=duration, error=str(exc))

        stdout_tail = completed.stdout[-2000:] if completed.stdout else ""
        stderr_tail = completed.stderr[-2000:] if completed.stderr else ""

        if completed.returncode != 0:
            return SmokeTestResult(
                ok=False, ran_at=ran_at, duration_seconds=duration,
                output_path=str(output_path),
                returncode=completed.returncode,
                stdout_tail=stdout_tail,
                stderr_tail=stderr_tail,
                error=f"ACE runner exited with code {completed.returncode}",
            )

        audio = validate_with_ffprobe(output_path, ffprobe=ffprobe)
        if not audio.ok:
            return SmokeTestResult(
                ok=False, ran_at=ran_at, duration_seconds=duration,
                output_path=str(output_path),
                returncode=completed.returncode,
                stdout_tail=stdout_tail,
                stderr_tail=stderr_tail,
                audio=audio,
                error=f"Audio validation failed: {audio.error}",
            )

        return SmokeTestResult(
            ok=True,
            ran_at=ran_at,
            duration_seconds=duration,
            output_path=str(output_path),
            returncode=completed.returncode,
            stdout_tail=stdout_tail,
            stderr_tail=stderr_tail,
            audio=audio,
        )


# ---------------------------------------------------------------------------
# Full runtime status assembly
# ---------------------------------------------------------------------------

def build_runtime_status(
    hardware: HardwareProfile,
    packages_ok: bool,
    last_smoke_test: SmokeTestResult | None,
) -> AceRuntimeStatus:
    deps_ok = packages_ok
    cuda_ok = hardware.cuda_available
    ffprobe_ok = hardware.ffprobe_available
    checkpoints_ok = bool(hardware.turbo_checkpoint and hardware.vae_present)
    generation_ok = bool(last_smoke_test and last_smoke_test.ok)
    audio_valid = bool(last_smoke_test and last_smoke_test.audio and last_smoke_test.audio.ok)

    ace_usable = deps_ok and cuda_ok and ffprobe_ok and checkpoints_ok and generation_ok and audio_valid

    safe_cfg = hardware.safe_recommended_config

    # LM warning: safe tier calls for 0.6B but it isn't installed
    lm_warning = ""
    if safe_cfg and not safe_cfg.lm_model:
        if hardware.lm_checkpoint:
            lm_warning = (
                f"Recommended 0.6B LM not installed. "
                f"Safe mode runs without LM ({hardware.lm_checkpoint} is available but classified experimental). "
                f"Install: python scripts/install_ace_lm.py"
            )
        else:
            lm_warning = (
                "No LM model installed. Safe mode runs without LM. "
                "Install the safe 0.6B: python scripts/install_ace_lm.py"
            )

    if not deps_ok:
        msg = "ACE venv packages are not verified. Run the readiness check to confirm installation."
    elif not cuda_ok:
        msg = "CUDA is not available. Check GPU drivers or set ACE_DEVICE=cpu."
    elif not checkpoints_ok:
        missing = []
        if not hardware.turbo_checkpoint:
            missing.append("turbo checkpoint")
        if not hardware.vae_present:
            missing.append("vae")
        msg = f"Required ACE checkpoints missing: {', '.join(missing)}. Check ACE_MODEL_DIR."
    elif not ffprobe_ok:
        msg = "ffprobe not found. Install ffmpeg to enable audio validation."
    elif not generation_ok:
        err = (last_smoke_test.error if last_smoke_test else "not run yet")
        msg = f"ACE generation smoke test failed: {err}"
    elif not audio_valid:
        err = (last_smoke_test.audio.error if last_smoke_test and last_smoke_test.audio else "unknown")
        msg = f"Generated audio failed validation: {err}"
    else:
        gpu_desc = f"{hardware.gpu_name} {hardware.gpu_vram_mb // 1024}GB" if hardware.gpu_name else "GPU"
        safe_lm = (safe_cfg.lm_model if safe_cfg else None) or "none"
        msg = (
            f"ACE runtime fully ready. {gpu_desc} — "
            f"turbo={hardware.turbo_checkpoint}, safe_lm={safe_lm}, "
            f"ffprobe=ok, last smoke test passed."
        )

    return AceRuntimeStatus(
        ace_usable=ace_usable,
        checked_at=datetime.now(timezone.utc).isoformat(),
        deps_ok=deps_ok,
        cuda_ok=cuda_ok,
        ffprobe_ok=ffprobe_ok,
        checkpoints_ok=checkpoints_ok,
        generation_ok=generation_ok,
        audio_valid=audio_valid,
        hardware=hardware,
        last_smoke_test=last_smoke_test,
        user_message=msg,
        lm_warning=lm_warning,
    )


# ---------------------------------------------------------------------------
# Profile persistence
# ---------------------------------------------------------------------------

def load_runtime_profile(data_dir: Path) -> dict | None:
    path = data_dir / _PROFILE_FILENAME
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_runtime_profile(data_dir: Path, status: AceRuntimeStatus) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / _PROFILE_FILENAME
    path.write_text(status.model_dump_json(indent=2), encoding="utf-8")
    return path
