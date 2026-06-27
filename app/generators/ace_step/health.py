from __future__ import annotations

import subprocess
from pathlib import Path

from app.core.command_template import validate_template
from app.core.config import Settings
from app.domain.models import ModelStatus
from app.generators.ace_step.env import ace_subprocess_env
from app.generators.ace_step.generation_history import find_verified_ace_generation

ACE_IMPORT_CHECKS = ("torch", "torchaudio", "transformers", "diffusers", "accelerate", "numpy")


def _exists(path: Path) -> bool:
    if str(path) == "python":
        return True
    return path.exists()


def _readiness_user_message(
    ace_enabled: bool,
    wiring_ok: bool,
    packages_checked: bool,
    packages_ok: bool | None,
    cuda_expected: bool,
    cuda_available: bool | None,
    cuda_ready: bool | None,
    first_real_generation_verified: bool,
    fallback_enabled: bool,
    warnings: list[str],
) -> str:
    if not ace_enabled:
        suffix = "Procedural fallback is active." if fallback_enabled else "Set ACE_ALLOW_FALLBACK=true to enable the procedural fallback."
        return f"ACE is disabled (ACE_ENABLED=false). {suffix}"
    if not wiring_ok:
        first = warnings[0] if warnings else "Check ACE_* settings."
        return f"ACE wiring not ready: {first}"
    if not packages_checked:
        return (
            "ACE wiring is ready. Run POST /api/model-status/test to verify packages and CUDA. "
            "The first real generation may take much longer while Hugging Face checkpoints download."
        )
    if packages_ok is False:
        return "ACE wiring is ready but ACE venv package imports failed. See missing_packages."
    if cuda_expected and cuda_ready is False:
        return "ACE packages are installed but CUDA is unavailable. Use ACE_DEVICE=cpu or fix the CUDA driver."
    if first_real_generation_verified:
        return "ACE is fully ready — wiring, packages, and CUDA verified; at least one real ACE generation succeeded."
    if cuda_ready:
        return (
            "ACE wiring, packages, and CUDA are ready. No verified ACE job in app history yet — "
            "first generation may take longer while checkpoints download to HF_CACHE_DIR."
        )
    return "ACE wiring looks complete. Run POST /api/model-status/test to verify package imports and CUDA."



def get_ace_status(settings: Settings) -> ModelStatus:
    warnings = validate_template(settings.ace_command_template)
    python_exists = _exists(settings.ace_python)
    script_exists = settings.ace_script.exists()
    model_dir_exists = settings.ace_model_dir.exists()
    command_configured = bool(settings.ace_command_template.strip())
    if settings.ace_enabled and not python_exists:
        warnings.append("ACE_PYTHON does not exist.")
    if settings.ace_enabled and not script_exists:
        warnings.append("ACE_SCRIPT does not exist.")
    if settings.ace_enabled and not model_dir_exists:
        warnings.append("ACE_MODEL_DIR does not exist.")
    command_template_valid = command_configured and not validate_template(settings.ace_command_template)
    can_generate = bool(settings.ace_enabled and command_template_valid and python_exists and script_exists and model_dir_exists)
    wiring_ok = can_generate

    hf_cache_configured = settings.hf_cache_dir is not None
    hf_cache_dir_str = ""
    hf_cache_exists = False
    if settings.hf_cache_dir is not None:
        hf_cache_dir_str = str(settings.hf_cache_dir.expanduser())
        hf_cache_exists = settings.hf_cache_dir.expanduser().exists()

    generation_proof = find_verified_ace_generation(settings.metadata_dir)
    first_verified = generation_proof is not None

    return ModelStatus(
        ace_enabled=settings.ace_enabled,
        ace_command_configured=command_configured,
        command_template_valid=command_template_valid,
        ace_python_exists=python_exists,
        ace_script_exists=script_exists,
        ace_model_dir_exists=model_dir_exists,
        wiring_ok=wiring_ok,
        cuda_expected=settings.ace_device.lower() == "cuda",
        can_generate=can_generate,
        fallback_enabled=settings.ace_allow_fallback,
        hf_cache_dir=hf_cache_dir_str,
        hf_cache_configured=hf_cache_configured,
        hf_cache_exists=hf_cache_exists,
        first_real_generation_verified=first_verified,
        first_real_generation=generation_proof,
        warnings=warnings,
        ace_python=str(settings.ace_python),
        ace_script=str(settings.ace_script),
        ace_model_dir=str(settings.ace_model_dir),
        user_message=_readiness_user_message(
            settings.ace_enabled,
            wiring_ok,
            False,
            None,
            settings.ace_device.lower() == "cuda",
            None,
            None,
            first_verified,
            settings.ace_allow_fallback,
            warnings,
        ),
    )


def enrich_status_with_packages(
    status: ModelStatus,
    packages: dict[str, object],
    diagnostic: dict[str, object] | None,
) -> ModelStatus:
    """Return a copy of status augmented with package and CUDA health from subprocess results."""
    missing: list[str] = list(packages.get("missing_packages") or [])  # type: ignore[arg-type]
    packages_ok = bool(packages.get("ok")) and not missing

    cuda_available: bool | None = None
    info = (diagnostic or {}).get("info") if diagnostic else None
    if isinstance(info, dict) and "cuda_available" in info:
        cuda_available = bool(info["cuda_available"])

    cuda_ready: bool | None = None
    if packages_ok:
        cuda_ready = (not status.cuda_expected) or bool(cuda_available)
    elif not packages_ok:
        cuda_ready = False

    user_message = _readiness_user_message(
        status.ace_enabled,
        status.wiring_ok,
        True,
        packages_ok,
        status.cuda_expected,
        cuda_available,
        cuda_ready,
        status.first_real_generation_verified,
        status.fallback_enabled,
        status.warnings,
    )

    return status.model_copy(update={
        "packages_checked": True,
        "packages_ok": packages_ok,
        "missing_packages": missing,
        "cuda_available": cuda_available,
        "cuda_ready": cuda_ready,
        "user_message": user_message,
    })


def run_ace_python_diagnostic(settings: Settings, timeout_seconds: int = 10) -> dict[str, object]:
    diagnostic_code = """
import json
import sys
info = {"python": sys.version.split()[0]}
try:
    import torch
    info.update({
        "torch": torch.__version__,
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_device_count": torch.cuda.device_count(),
    })
except Exception as exc:
    info.update({
        "torch": None,
        "cuda_available": False,
        "cuda_device_count": 0,
        "torch_error": str(exc),
    })
print(json.dumps(info))
"""
    cmd = [str(settings.ace_python), "-c", diagnostic_code]
    try:
        completed = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_seconds, check=False, env=ace_subprocess_env(settings))
        parsed: dict[str, object] = {}
        if completed.stdout.strip():
            import json
            parsed = json.loads(completed.stdout.strip())
        return {
            "ok": completed.returncode == 0,
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
            "info": parsed,
        }
    except Exception as exc:
        return {"ok": False, "command": cmd, "message": str(exc)}


def check_ace_packages(settings: Settings, timeout_seconds: int = 15) -> dict[str, object]:
    package_list = ", ".join(repr(pkg) for pkg in ACE_IMPORT_CHECKS)
    check_code = f"""
import json
checks = {{}}
for pkg in [{package_list}]:
    try:
        mod = __import__(pkg)
        checks[pkg] = getattr(mod, "__version__", "ok")
    except Exception as exc:
        checks[pkg] = f"missing: {{exc}}"
print(json.dumps(checks))
"""
    cmd = [str(settings.ace_python), "-c", check_code]
    try:
        completed = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_seconds, check=False, env=ace_subprocess_env(settings))
        import json
        packages: dict[str, str] = {}
        if completed.stdout.strip():
            packages = json.loads(completed.stdout.strip())
        missing = [name for name, value in packages.items() if str(value).startswith("missing:")]
        return {
            "ok": completed.returncode == 0 and not missing,
            "command": cmd,
            "returncode": completed.returncode,
            "packages": packages,
            "missing_packages": missing,
            "stderr": completed.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "command": cmd, "message": str(exc), "packages": {}, "missing_packages": list(ACE_IMPORT_CHECKS)}


def run_ace_runner_dry_run(settings: Settings, timeout_seconds: int = 20) -> dict[str, object]:
    if not settings.ace_script.exists():
        return {"ok": False, "skipped": True, "message": "ACE_SCRIPT does not exist"}
    cmd = [str(settings.ace_python), str(settings.ace_script), "--dry-run"]
    try:
        completed = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_seconds, check=False, env=ace_subprocess_env(settings))
        return {
            "ok": completed.returncode == 0,
            "command": cmd,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "command": cmd, "message": str(exc)}


def recommended_actions(
    status: ModelStatus,
    diagnostic: dict[str, object] | None = None,
    packages: dict[str, object] | None = None,
    dry_run: dict[str, object] | None = None,
) -> list[str]:
    actions: list[str] = []
    if not status.ace_enabled:
        actions.append("Set ACE_ENABLED=true in .env when your ACE venv is ready.")
    if not status.ace_command_configured:
        actions.append("Set ACE_COMMAND_TEMPLATE in .env (see docs/ACE_STEP_SETUP.md).")
    if status.ace_enabled and not status.ace_python_exists:
        actions.append(f"Create or fix ACE_PYTHON at {status.ace_python}.")
    if status.ace_enabled and not status.ace_script_exists:
        actions.append(f"Install or copy ace_runner.py to {status.ace_script}.")
    if status.ace_enabled and not status.ace_model_dir_exists:
        actions.append(f"Download ACE-Step checkpoints to {status.ace_model_dir}.")
    if packages and packages.get("missing_packages"):
        missing = packages["missing_packages"]
        actions.append(f"Install missing ACE venv packages: {', '.join(missing)}.")
    info = (diagnostic or {}).get("info") if diagnostic else None
    if isinstance(info, dict) and info.get("torch") is None:
        actions.append("Install torch in the ACE venv: pip install torch torchaudio.")
    if status.cuda_expected and isinstance(info, dict) and info.get("cuda_available") is False:
        actions.append("CUDA is not available in ACE_PYTHON — use ACE_DEVICE=cpu or install CUDA-enabled torch.")
    if dry_run and not dry_run.get("ok") and not dry_run.get("skipped"):
        actions.append("Fix ace_runner.py --dry-run (runner bridge must respond before full inference).")
    if status.can_generate and not actions:
        actions.append("ACE wiring looks ready — run: python scripts/ace_smoke_test.py --dry-run-only")
    return actions
