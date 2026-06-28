"""
Hardware detection for ACE-Step runtime readiness.

Detects GPU (CUDA), VRAM, ffmpeg/ffprobe, and available ACE checkpoints,
then produces three configuration tiers:
  safe_recommended_config   — conservative defaults per ACE tier guidelines
  detected_available_config — what's actually installed (may exceed safe tier)
  experimental_config_options — options above the safe tier for advanced use
"""
from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from app.core.ace_profiles import (
    AceRenderProfile,
    build_final_render_profiles,
    final_sft_installed,
)

# Checkpoint subfolder names we recognise, in preference order
_TURBO_NAMES = ["acestep-v15-turbo", "acestep-v1-turbo", "acestep-v1"]
_SFT_NAMES = ["acestep-v15-sft", "acestep-v15-base"]
# 0.6B is ACE's recommended safe tier; 1.7B is advanced/higher VRAM
_LM_SAFE_NAMES = ["acestep-5Hz-lm-0.6B"]
_LM_ADVANCED_NAMES = ["acestep-5Hz-lm-1.7B"]
_LM_ALL_NAMES = _LM_SAFE_NAMES + _LM_ADVANCED_NAMES


class AceGenConfig(BaseModel):
    """A complete set of ACE generation parameters for one hardware tier."""
    checkpoint: str = ""            # e.g. "acestep-v15-turbo"
    lm_model: str = ""              # e.g. "acestep-5Hz-lm-0.6B", or "" for no LM
    batch_size: int = 1
    duration: int = 10
    inference_steps: int = 8
    offload_to_cpu: bool = True
    device: str = "cuda"
    description: str = ""          # human-readable label for this tier


class HardwareProfile(BaseModel):
    detected_at: str = ""

    # GPU / CUDA
    gpu_name: str = ""
    gpu_vram_mb: int = 0
    gpu_count: int = 0
    cuda_available: bool = False
    cuda_version: str = ""

    # ffmpeg tools
    ffmpeg_path: str = ""
    ffprobe_path: str = ""
    ffmpeg_available: bool = False
    ffprobe_available: bool = False

    # ACE checkpoints
    checkpoint_dir: str = ""
    checkpoint_dir_exists: bool = False
    turbo_checkpoint: str = ""      # subfolder name found, e.g. "acestep-v15-turbo"
    sft_checkpoint: str = ""        # non-turbo DiT for 24–50 step generation
    final_sft_available: bool = False # acestep-v15-sft weights present
    lm_checkpoint: str = ""         # highest-tier LM found (may be advanced)
    lm_safe_checkpoint: str = ""    # safe-tier LM found (0.6B), or ""
    vae_present: bool = False
    config_present: bool = False
    available_checkpoints: list[str] = []

    # Three-tier configuration
    safe_recommended_config: AceGenConfig | None = None
    detected_available_config: AceGenConfig | None = None
    experimental_config_options: list[AceGenConfig] = []
    final_render_profiles: list[AceRenderProfile] = []


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def detect_gpu_via_nvidia_smi() -> dict[str, object]:
    """Query nvidia-smi for GPU name and VRAM."""
    smi = shutil.which("nvidia-smi")
    if not smi:
        return {}
    try:
        result = subprocess.run(
            [smi, "--query-gpu=name,memory.total,count", "--format=csv,noheader,nounits"],
            text=True, capture_output=True, timeout=10, check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        lines = [ln.strip() for ln in result.stdout.strip().splitlines() if ln.strip()]
        if not lines:
            return {}
        parts = lines[0].split(",")
        if len(parts) < 2:
            return {}
        return {
            "gpu_name": parts[0].strip(),
            "gpu_vram_mb": int(parts[1].strip()),
            "gpu_count": len(lines),
        }
    except Exception:
        return {}


def detect_cuda_via_torch(ace_python: Path, env: dict[str, str] | None = None) -> dict[str, object]:
    """Query CUDA availability via the ACE venv's own Python subprocess."""
    code = """
import json, sys
info = {"python": sys.version.split()[0], "cuda": False, "cuda_version": "", "devices": []}
try:
    import torch
    info["cuda"] = torch.cuda.is_available()
    info["cuda_version"] = torch.version.cuda or ""
    info["devices"] = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
except Exception as exc:
    info["torch_error"] = str(exc)
print(json.dumps(info))
"""
    try:
        result = subprocess.run(
            [str(ace_python), "-c", code],
            text=True, capture_output=True, timeout=20, check=False, env=env,
        )
        if result.stdout.strip():
            return json.loads(result.stdout.strip())
    except Exception:
        pass
    return {}


def detect_ffmpeg() -> dict[str, str]:
    return {
        "ffmpeg": shutil.which("ffmpeg") or "",
        "ffprobe": shutil.which("ffprobe") or "",
    }


def scan_checkpoints(checkpoint_dir: Path) -> dict[str, object]:
    """Scan a checkpoint directory for known ACE model artefacts."""
    if not checkpoint_dir.exists():
        return {
            "exists": False, "available": [],
            "turbo": "", "sft": "", "lm": "", "lm_safe": "",
            "vae": False, "config": False,
        }
    entries = {p.name for p in checkpoint_dir.iterdir()} if checkpoint_dir.is_dir() else set()
    turbo = next((n for n in _TURBO_NAMES if n in entries), "")
    sft = next((n for n in _SFT_NAMES if n in entries), "")
    lm_safe = next((n for n in _LM_SAFE_NAMES if n in entries), "")
    # Best available LM: prefer safe, fall back to advanced
    lm = lm_safe or next((n for n in _LM_ADVANCED_NAMES if n in entries), "")
    return {
        "exists": True,
        "available": sorted(entries),
        "turbo": turbo,
        "sft": sft,
        "lm": lm,
        "lm_safe": lm_safe,
        "vae": "vae" in entries,
        "config": "config.json" in entries,
    }


# ---------------------------------------------------------------------------
# Config tier selection
# ---------------------------------------------------------------------------

def _make_configs(
    gpu_vram_mb: int,
    turbo: str,
    sft: str,
    lm_safe: str,
    lm_advanced: str,
    checkpoint_dir: Path,
) -> tuple[AceGenConfig, AceGenConfig, list[AceGenConfig]]:
    """
    Return (safe_recommended, detected_available, experimental_options).

    Safe tier follows ACE's own recommendations:
    - RTX 3060 12GB (tier4): turbo checkpoint, 0.6B LM (if present), batch=1,
      steps=8, offload=True.  No LM when only 1.7B is available (too large for safe).
    - < 10 GB VRAM: same but always offload, no LM.
    - >= 16 GB VRAM: offload optional, could run 1.7B safely.
    """
    if gpu_vram_mb >= 16_000:
        offload = False
        safe_steps = 12
        device = "cuda"
    elif gpu_vram_mb >= 10_000:
        # RTX 3060 12GB territory — this is the common case
        offload = True
        safe_steps = 8
        device = "cuda"
    elif gpu_vram_mb > 0:
        offload = True
        safe_steps = 8
        device = "cuda"
    else:
        offload = True
        safe_steps = 8
        device = "cpu"

    # Safe config: use 0.6B if present; skip LM entirely if only 1.7B is available
    safe_lm = lm_safe  # "" when 0.6B not installed
    safe_cfg = AceGenConfig(
        checkpoint=turbo,
        lm_model=safe_lm,
        batch_size=1,
        duration=10,
        inference_steps=safe_steps,
        offload_to_cpu=offload,
        device=device,
        description=(
            f"Safe tier — turbo checkpoint"
            + (f", {safe_lm}" if safe_lm else ", no LM (0.6B not installed)")
            + f", {safe_steps} steps, offload={offload}"
        ),
    )

    # Detected config: use the best LM that's actually on disk
    detected_lm = lm_safe or lm_advanced
    detected_cfg = AceGenConfig(
        checkpoint=turbo,
        lm_model=detected_lm,
        batch_size=1,
        duration=10,
        inference_steps=safe_steps,
        offload_to_cpu=offload,
        device=device,
        description=(
            f"Installed — turbo checkpoint"
            + (f", {detected_lm}" if detected_lm else ", no LM")
            + f", {safe_steps} steps, offload={offload}"
        ),
    )

    # Experimental: options that exceed safe tier
    experimental: list[AceGenConfig] = []
    # 1.7B LM is experimental on < 16 GB VRAM
    if lm_advanced and gpu_vram_mb < 16_000:
        experimental.append(AceGenConfig(
            checkpoint=turbo,
            lm_model=lm_advanced,
            batch_size=1,
            duration=10,
            inference_steps=safe_steps,
            offload_to_cpu=offload,
            device=device,
            description=f"Experimental — {lm_advanced} (higher VRAM; monitor for OOM on {gpu_vram_mb // 1024}GB)",
        ))
    # More turbo steps are clamped by ACE; list as experimental for awareness only
    if turbo and not sft:
        experimental.append(AceGenConfig(
            checkpoint=turbo,
            lm_model=safe_lm,
            batch_size=1,
            duration=10,
            inference_steps=24,
            offload_to_cpu=offload,
            device=device,
            description="Experimental — 24 steps requested but turbo clamps to 8; install acestep-v15-sft",
        ))

    if sft:
        for profile in build_final_render_profiles(checkpoint_dir):
            experimental.append(AceGenConfig(
                checkpoint=profile.checkpoint,
                lm_model=profile.lm_model,
                batch_size=profile.batch_size,
                duration=60,
                inference_steps=profile.inference_steps,
                offload_to_cpu=profile.offload_to_cpu,
                device=device,
                description=f"{profile.name} — {profile.description}",
            ))

    return safe_cfg, detected_cfg, experimental


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_hardware_profile(
    checkpoint_dir: Path,
    ace_python: Path | None = None,
    ace_env: dict[str, str] | None = None,
) -> HardwareProfile:
    """
    Assemble a full HardwareProfile by probing the local system.

    Calls nvidia-smi for GPU/VRAM, optionally probes ACE venv for CUDA,
    checks ffmpeg/ffprobe, and scans the checkpoint directory.
    """
    now = datetime.now(timezone.utc).isoformat()

    gpu_info = detect_gpu_via_nvidia_smi()
    gpu_name: str = str(gpu_info.get("gpu_name", ""))
    gpu_vram_mb: int = int(gpu_info.get("gpu_vram_mb", 0))
    gpu_count: int = int(gpu_info.get("gpu_count", 0))
    cuda_available = gpu_count > 0

    cuda_version = ""
    if ace_python and ace_python.exists():
        torch_info = detect_cuda_via_torch(ace_python, ace_env)
        cuda_available = bool(torch_info.get("cuda", cuda_available))
        cuda_version = str(torch_info.get("cuda_version", ""))

    ff = detect_ffmpeg()
    ckpt = scan_checkpoints(checkpoint_dir)

    # Resolve what's present on disk
    turbo: str = ckpt["turbo"]      # type: ignore[assignment]
    sft: str = ckpt["sft"]          # type: ignore[assignment]
    lm: str = ckpt["lm"]            # type: ignore[assignment]
    lm_safe: str = ckpt["lm_safe"]  # type: ignore[assignment]
    lm_advanced = next((n for n in _LM_ADVANCED_NAMES if n in (ckpt["available"] or [])), "")  # type: ignore[arg-type]

    safe_cfg, detected_cfg, experimental = _make_configs(
        gpu_vram_mb, turbo, sft, lm_safe, lm_advanced, checkpoint_dir,
    )
    final_profiles = build_final_render_profiles(checkpoint_dir)

    return HardwareProfile(
        detected_at=now,
        gpu_name=gpu_name,
        gpu_vram_mb=gpu_vram_mb,
        gpu_count=gpu_count,
        cuda_available=cuda_available,
        cuda_version=cuda_version,
        ffmpeg_path=ff["ffmpeg"],
        ffprobe_path=ff["ffprobe"],
        ffmpeg_available=bool(ff["ffmpeg"]),
        ffprobe_available=bool(ff["ffprobe"]),
        checkpoint_dir=str(checkpoint_dir),
        checkpoint_dir_exists=bool(ckpt["exists"]),
        turbo_checkpoint=turbo,
        sft_checkpoint=sft,
        final_sft_available=final_sft_installed(checkpoint_dir),
        lm_checkpoint=lm,
        lm_safe_checkpoint=lm_safe,
        vae_present=bool(ckpt["vae"]),
        config_present=bool(ckpt["config"]),
        available_checkpoints=list(ckpt["available"]),  # type: ignore[arg-type]
        safe_recommended_config=safe_cfg,
        detected_available_config=detected_cfg,
        experimental_config_options=experimental,
        final_render_profiles=final_profiles,
    )
