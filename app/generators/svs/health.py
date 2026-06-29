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

    if settings.svs_backend == "diffsinger" and settings.svs_enabled:
        tiger_dir = settings.svs_tiger_dir
        if tiger_dir is None:
            warnings.append("SVS_TIGER_DIR is not set (required for diffsinger backend).")
            command_ready = False
        else:
            tiger_expanded = tiger_dir.expanduser()
            if not tiger_expanded.exists():
                warnings.append(f"SVS_TIGER_DIR does not exist: {tiger_dir}")
                command_ready = False
            elif not (tiger_expanded / "dsacoustic" / "acoustic.onnx").exists():
                warnings.append(
                    f"SVS_TIGER_DIR/dsacoustic/acoustic.onnx not found — TIGER pack may be incomplete."
                )
                command_ready = False

    can_generate = bool(settings.svs_enabled and command_ready)

    return {
        "svs_enabled": settings.svs_enabled,
        "svs_backend": settings.svs_backend,
        "can_generate": can_generate,
        "svs_allow_fallback": settings.svs_allow_fallback,
        "svs_python": str(python_path),
        "svs_script": str(script_path),
        "svs_model_dir": str(model_dir),
        "svs_tiger_dir": str(settings.svs_tiger_dir) if settings.svs_tiger_dir else None,
        "warnings": warnings,
        "status": "ready" if can_generate else ("fallback-ready" if settings.svs_allow_fallback else "not-configured"),
    }
