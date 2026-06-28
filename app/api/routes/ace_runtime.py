"""
ACE Runtime Status API.

GET  /api/ace-runtime-status        — returns persisted profile + live hardware snapshot
POST /api/ace-runtime-status/validate — runs full smoke test, persists result
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.ace_runtime import (
    AceRuntimeStatus,
    SmokeTestResult,
    build_runtime_status,
    load_runtime_profile,
    run_smoke_test,
    save_runtime_profile,
)
from app.core.config import Settings, get_settings
from app.core.hardware import HardwareProfile, build_hardware_profile
from app.generators.ace_step.env import ace_subprocess_env
from app.generators.ace_step.health import check_ace_packages

router = APIRouter(prefix="/api", tags=["ace-runtime"])


def _hardware(settings: Settings) -> HardwareProfile:
    checkpoint_dir = settings.ace_model_dir.expanduser()
    ace_python = settings.ace_python if settings.ace_python != "python" else None  # type: ignore[comparison-overlap]
    ace_python_path = settings.ace_python if ace_python else None
    return build_hardware_profile(
        checkpoint_dir=checkpoint_dir,
        ace_python=ace_python_path,
        ace_env=ace_subprocess_env(settings),
    )


def _recommended_duration(hw: HardwareProfile) -> int:
    if hw.safe_recommended_config is not None:
        return hw.safe_recommended_config.duration
    return 10


@router.get("/ace-runtime-status", response_model=AceRuntimeStatus)
def ace_runtime_status(settings: Settings = Depends(get_settings)) -> AceRuntimeStatus:
    """
    Fast status check. Returns the persisted hardware profile and last smoke test result.
    Does NOT re-run generation. Call POST /validate to refresh.
    """
    # Try loading fully-persisted status first
    raw = load_runtime_profile(settings.data_dir)
    if raw is not None:
        try:
            return AceRuntimeStatus.model_validate(raw)
        except Exception:
            pass

    # Fall back to a live hardware snapshot with no smoke-test data
    hw = _hardware(settings)
    packages = check_ace_packages(settings)
    packages_ok = bool(packages.get("ok")) and not packages.get("missing_packages")
    return build_runtime_status(hw, packages_ok=packages_ok, last_smoke_test=None)


@router.post("/ace-runtime-status/validate", response_model=AceRuntimeStatus)
def ace_runtime_validate(
    settings: Settings = Depends(get_settings),
) -> AceRuntimeStatus:
    """
    Full validation — detects hardware, checks packages, runs a generation smoke test,
    validates the audio with ffprobe, and persists results to data/ace_hardware_profile.json.

    Only marks ace_usable=True when ALL gates pass:
    deps, CUDA, checkpoints, ffprobe, generation, audio validation.

    Warning: this may take several minutes on first run (checkpoint loading).
    """
    hw = _hardware(settings)

    packages = check_ace_packages(settings)
    packages_ok = bool(packages.get("ok")) and not packages.get("missing_packages")

    smoke: SmokeTestResult | None = None
    duration = _recommended_duration(hw)
    if packages_ok and hw.cuda_available and hw.checkpoint_dir_exists and hw.turbo_checkpoint:
        ffprobe = hw.ffprobe_path or "ffprobe"
        smoke = run_smoke_test(
            ace_python=settings.ace_python,
            ace_script=settings.ace_script,
            ace_model_dir=settings.ace_model_dir.expanduser(),
            ace_device=settings.ace_device,
            ace_env=ace_subprocess_env(settings),
            timeout_seconds=settings.ace_timeout_seconds,
            duration=duration,
            ffprobe=ffprobe,
        )
    elif not packages_ok:
        smoke = SmokeTestResult(
            ok=False, ran_at="", duration_seconds=duration,
            error="Skipped: ACE packages not installed",
        )
    elif not hw.cuda_available:
        smoke = SmokeTestResult(
            ok=False, ran_at="", duration_seconds=duration,
            error="Skipped: CUDA not available",
        )
    elif not hw.checkpoint_dir_exists or not hw.turbo_checkpoint:
        smoke = SmokeTestResult(
            ok=False, ran_at="", duration_seconds=duration,
            error="Skipped: turbo checkpoint not found in ACE_MODEL_DIR",
        )

    status = build_runtime_status(hw, packages_ok=packages_ok, last_smoke_test=smoke)
    save_runtime_profile(settings.data_dir, status)
    return status
