from pathlib import Path

from app.core.config import Settings
from app.generators.ace_step.env import ace_subprocess_env


def test_ace_subprocess_env_uses_shared_hf_cache(tmp_path):
    cache_dir = tmp_path / "hf-cache"
    checkpoints_dir = tmp_path / "ace-checkpoints"
    ace_step_dir = tmp_path / "ACE-Step-1.5"
    settings = Settings(DATA_DIR=tmp_path, ACE_STEP_DIR=ace_step_dir, HF_CACHE_DIR=cache_dir, ACE_MODEL_DIR=checkpoints_dir)
    env = ace_subprocess_env(settings)
    assert env["ACE_STEP_DIR"] == str(ace_step_dir)
    assert env["HF_HOME"] == str(cache_dir)
    assert env["HUGGINGFACE_HUB_CACHE"] == str(cache_dir / "hub")
    assert env["TRANSFORMERS_CACHE"] == str(cache_dir / "transformers")
    assert env["DIFFUSERS_CACHE"] == str(cache_dir / "diffusers")
    assert env["ACESTEP_CHECKPOINTS_DIR"] == str(checkpoints_dir)


def test_ace_subprocess_env_keeps_existing_env_without_cache(tmp_path):
    settings = Settings(DATA_DIR=tmp_path, HF_CACHE_DIR=None)
    env = ace_subprocess_env(settings)
    assert isinstance(env, dict)
    assert env.get("HF_HOME") != str(Path("__unused__"))
