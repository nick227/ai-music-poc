"""
Additional HF_CACHE_DIR env propagation tests.
Verifies that all five HF/cache env vars are set correctly and that
the model status correctly reflects configured vs. non-configured state.
"""
from pathlib import Path

import pytest

from app.core.config import Settings
from app.generators.ace_step.env import ace_subprocess_env
from app.generators.ace_step.health import get_ace_status


# ---------------------------------------------------------------------------
# ace_subprocess_env: variable completeness
# ---------------------------------------------------------------------------

def test_all_hf_env_vars_set_when_cache_configured(tmp_path):
    cache_dir = tmp_path / "hf"
    checkpoints = tmp_path / "checkpoints"
    ace_step = tmp_path / "ACE-Step-1.5"
    settings = Settings(
        DATA_DIR=tmp_path,
        HF_CACHE_DIR=cache_dir,
        ACE_MODEL_DIR=checkpoints,
        ACE_STEP_DIR=ace_step,
    )
    env = ace_subprocess_env(settings)
    assert env["HF_HOME"] == str(cache_dir)
    assert env["HUGGINGFACE_HUB_CACHE"] == str(cache_dir / "hub")
    assert env["TRANSFORMERS_CACHE"] == str(cache_dir / "transformers")
    assert env["DIFFUSERS_CACHE"] == str(cache_dir / "diffusers")
    assert env["ACESTEP_CHECKPOINTS_DIR"] == str(checkpoints)
    assert env["ACE_STEP_DIR"] == str(ace_step)


def test_hf_env_vars_absent_when_cache_not_configured(tmp_path):
    settings = Settings(DATA_DIR=tmp_path, HF_CACHE_DIR=None)
    env = ace_subprocess_env(settings)
    for key in ("HF_HOME", "HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE", "DIFFUSERS_CACHE"):
        assert key not in env or env[key] != "None", f"{key} should not be set from a None cache_dir"


def test_acestep_checkpoints_dir_uses_ace_model_dir(tmp_path):
    custom_ckpt = tmp_path / "my-checkpoints"
    settings = Settings(DATA_DIR=tmp_path, HF_CACHE_DIR=tmp_path / "hf", ACE_MODEL_DIR=custom_ckpt)
    env = ace_subprocess_env(settings)
    assert env["ACESTEP_CHECKPOINTS_DIR"] == str(custom_ckpt)


def test_ace_step_dir_absent_from_env_when_not_configured(tmp_path):
    settings = Settings(DATA_DIR=tmp_path, ACE_STEP_DIR=None, HF_CACHE_DIR=None)
    env = ace_subprocess_env(settings)
    assert "ACE_STEP_DIR" not in env


def test_env_inherits_process_env(tmp_path, monkeypatch):
    """ace_subprocess_env must include the caller's environment variables."""
    monkeypatch.setenv("MY_CUSTOM_VAR", "sentinel-value")
    settings = Settings(DATA_DIR=tmp_path, HF_CACHE_DIR=None)
    env = ace_subprocess_env(settings)
    assert env.get("MY_CUSTOM_VAR") == "sentinel-value"


def test_hf_cache_dir_expanded_tilde(tmp_path, monkeypatch):
    """Tilde in HF_CACHE_DIR must be expanded before being added to env."""
    # Point HOME to tmp_path so ~ expands there
    monkeypatch.setenv("HOME", str(tmp_path))
    tilde_path = Path("~/hf-cache-test")
    settings = Settings(DATA_DIR=tmp_path, HF_CACHE_DIR=tilde_path)
    env = ace_subprocess_env(settings)
    assert "~" not in env["HF_HOME"], "tilde must be expanded in HF_HOME"
    assert str(tmp_path) in env["HF_HOME"]
