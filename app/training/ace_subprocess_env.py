from __future__ import annotations

import os
from pathlib import Path


def ace_training_env(*, ace_step_dir: Path, base: dict[str, str] | None = None) -> dict[str, str]:
    """Build subprocess env with CUDA/FFmpeg library paths for ACE training."""
    env = dict(base or os.environ)
    env["ACE_STEP_DIR"] = str(ace_step_dir.resolve())

    python_paths = [str(ace_step_dir.resolve())]
    shim_root = Path(__file__).resolve().parents[2]
    python_paths.append(str(shim_root))
    existing_py = env.get("PYTHONPATH", "")
    if existing_py:
        python_paths.append(existing_py)
    env["PYTHONPATH"] = ":".join(python_paths)

    lib_dirs: list[Path] = []
    venv = ace_step_dir / ".venv" / "lib" / "python3.12" / "site-packages" / "nvidia"
    for name in ("cu13", "cuda_nvrtc", "cublas"):
        candidate = venv / name / "lib"
        if candidate.is_dir():
            lib_dirs.append(candidate)

    fallback_cu13 = Path(
        "/home/administrator/web/ltx-env/.venv/lib/python3.12/site-packages/nvidia/cu13/lib"
    )
    if fallback_cu13.is_dir():
        lib_dirs.append(fallback_cu13)

    ffmpeg_lib = Path(__file__).resolve().parents[2] / "tools" / "ffmpeg" / "lib"
    if ffmpeg_lib.is_dir():
        lib_dirs.append(ffmpeg_lib)

    if lib_dirs:
        joined = ":".join(str(path) for path in lib_dirs)
        existing = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{joined}:{existing}" if existing else joined

    env.setdefault("ACE_TRAIN_SAFE_ROOT", str(ace_step_dir.resolve().parent.parent))

    return env
