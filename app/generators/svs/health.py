from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.generators.svs.command_builder import validate_svs_template


def get_svs_status(settings: Settings) -> dict[str, object]:
    warnings: list[str] = []
    if settings.svs_command_template.strip():
        warnings.extend(validate_svs_template(settings.svs_command_template))
    python_path = settings.svs_python.expanduser()
    script_path = settings.svs_script.expanduser()
    model_dir = settings.svs_model_dir.expanduser()

    if settings.svs_enabled and not python_path.exists():
        warnings.append("SVS_PYTHON does not exist.")
    if settings.svs_enabled and not script_path.exists():
        warnings.append("SVS_SCRIPT does not exist.")
    if settings.svs_enabled and not model_dir.exists():
        warnings.append("SVS_MODEL_DIR does not exist (optional until external backend is wired).")

    command_ready = script_path.exists()
    can_generate = bool(settings.svs_enabled and command_ready)

    return {
        "svs_enabled": settings.svs_enabled,
        "can_generate": can_generate,
        "svs_allow_fallback": settings.svs_allow_fallback,
        "svs_python": str(python_path),
        "svs_script": str(script_path),
        "svs_model_dir": str(model_dir),
        "warnings": warnings,
        "status": "ready" if can_generate else ("fallback-ready" if settings.svs_allow_fallback else "not-configured"),
    }
