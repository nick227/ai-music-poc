from __future__ import annotations

import os

from app.core.config import Settings


def ace_subprocess_env(settings: Settings) -> dict[str, str]:
    env = os.environ.copy()
    if settings.hf_cache_dir is None:
        return env

    cache_dir = settings.hf_cache_dir.expanduser()
    env["HF_HOME"] = str(cache_dir)
    env["HUGGINGFACE_HUB_CACHE"] = str(cache_dir / "hub")
    env["TRANSFORMERS_CACHE"] = str(cache_dir / "transformers")
    env["DIFFUSERS_CACHE"] = str(cache_dir / "diffusers")
    return env
