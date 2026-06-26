from __future__ import annotations

import subprocess
from pathlib import Path

from app.core.command_template import validate_template
from app.core.config import Settings
from app.domain.models import ModelStatus
from app.generators.ace_step.env import ace_subprocess_env

ACE_IMPORT_CHECKS = ("torch", "torchaudio", "transformers", "diffusers", "accelerate", "numpy")


def _exists(path: Path) -> bool:
    if str(path) == "python":
        return True
    return path.exists()


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
    return ModelStatus(
        ace_enabled=settings.ace_enabled,
        ace_command_configured=command_configured,
        ace_python_exists=python_exists,
        ace_script_exists=script_exists,
        ace_model_dir_exists=model_dir_exists,
        cuda_expected=settings.ace_device.lower() == "cuda",
        command_template_valid=command_template_valid,
        can_generate=can_generate,
        fallback_enabled=settings.ace_allow_fallback,
        warnings=warnings,
        ace_python=str(settings.ace_python),
        ace_script=str(settings.ace_script),
        ace_model_dir=str(settings.ace_model_dir),
        hf_cache_dir=str(settings.hf_cache_dir) if settings.hf_cache_dir else "",
    )


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
