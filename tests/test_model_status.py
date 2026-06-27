from pathlib import Path

import pytest

from app.core.config import Settings
from app.domain.models import ModelStatus
from app.generators.ace_step.health import (
    enrich_status_with_packages,
    get_ace_status,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _wired_settings(tmp_path: Path) -> Settings:
    """Settings where all wiring paths exist (no real ACE venv needed).

    Explicitly overrides ACE_DEVICE and HF_CACHE_DIR so tests are not
    influenced by whatever is in the developer's .env file.
    """
    script = tmp_path / "ace_runner.py"
    script.write_text("# stub")
    model_dir = tmp_path / "ace-model"
    model_dir.mkdir()
    return Settings(
        DATA_DIR=tmp_path,
        ACE_ENABLED=True,
        ACE_PYTHON=Path("python"),
        ACE_SCRIPT=script,
        ACE_MODEL_DIR=model_dir,
        ACE_COMMAND_TEMPLATE="$python $script --prompt-file $prompt_file --output $output_path",
        ACE_DEVICE="cpu",    # isolate from .env; avoids cuda_expected=True in status
        HF_CACHE_DIR=None,   # isolate from .env
    )


# ---------------------------------------------------------------------------
# Existing coverage (kept for regression)
# ---------------------------------------------------------------------------

def test_model_status_reports_fallback(client):
    c, _ = client
    res = c.get("/api/model-status")
    assert res.status_code == 200
    body = res.json()
    assert body["fallback_enabled"] is True
    assert body["can_generate"] is False


def test_model_status_includes_paths(client):
    c, _ = client
    body = c.get("/api/model-status").json()
    assert "ace_python" in body
    assert "ace_script" in body
    assert "ace_model_dir" in body


# ---------------------------------------------------------------------------
# Wiring layer
# ---------------------------------------------------------------------------

def test_wiring_ok_false_when_ace_disabled(tmp_path):
    settings = Settings(DATA_DIR=tmp_path, ACE_ENABLED=False, ACE_COMMAND_TEMPLATE="")
    status = get_ace_status(settings)
    assert status.wiring_ok is False
    assert status.can_generate is False


def test_wiring_ok_true_when_all_paths_present(tmp_path):
    settings = _wired_settings(tmp_path)
    status = get_ace_status(settings)
    assert status.ace_enabled is True
    assert status.ace_python_exists is True
    assert status.ace_script_exists is True
    assert status.ace_model_dir_exists is True
    assert status.command_template_valid is True
    assert status.wiring_ok is True
    assert status.can_generate is True


def test_wiring_ok_false_when_model_dir_missing(tmp_path):
    script = tmp_path / "ace_runner.py"
    script.write_text("# stub")
    settings = Settings(
        DATA_DIR=tmp_path,
        ACE_ENABLED=True,
        ACE_PYTHON=Path("python"),
        ACE_SCRIPT=script,
        ACE_MODEL_DIR=tmp_path / "does-not-exist",
        ACE_COMMAND_TEMPLATE="$python $script --output $output_path --prompt-file $prompt_file",
    )
    status = get_ace_status(settings)
    assert status.ace_model_dir_exists is False
    assert status.wiring_ok is False
    assert status.can_generate is False


def test_wiring_ok_false_when_template_missing_output_token(tmp_path):
    script = tmp_path / "runner.py"
    script.write_text("#")
    model_dir = tmp_path / "m"
    model_dir.mkdir()
    settings = Settings(
        DATA_DIR=tmp_path,
        ACE_ENABLED=True,
        ACE_PYTHON=Path("python"),
        ACE_SCRIPT=script,
        ACE_MODEL_DIR=model_dir,
        ACE_COMMAND_TEMPLATE="$python $script --prompt-file $prompt_file",  # missing $output_path
    )
    status = get_ace_status(settings)
    assert status.command_template_valid is False
    assert status.wiring_ok is False
    assert any("output_path" in w for w in status.warnings)


# ---------------------------------------------------------------------------
# HF cache / checkpoint paths
# ---------------------------------------------------------------------------

def test_hf_cache_not_configured_by_default(tmp_path):
    settings = Settings(DATA_DIR=tmp_path, HF_CACHE_DIR=None)
    status = get_ace_status(settings)
    assert status.hf_cache_configured is False
    assert status.hf_cache_exists is False
    assert status.hf_cache_dir == ""


def test_hf_cache_configured_but_path_missing(tmp_path):
    nonexistent = tmp_path / "hf-cache-missing"
    settings = Settings(DATA_DIR=tmp_path, HF_CACHE_DIR=nonexistent)
    status = get_ace_status(settings)
    assert status.hf_cache_configured is True
    assert status.hf_cache_exists is False
    assert str(nonexistent) in status.hf_cache_dir


def test_hf_cache_configured_and_exists(tmp_path):
    cache_dir = tmp_path / "hf-cache"
    cache_dir.mkdir()
    settings = Settings(DATA_DIR=tmp_path, HF_CACHE_DIR=cache_dir)
    status = get_ace_status(settings)
    assert status.hf_cache_configured is True
    assert status.hf_cache_exists is True


# ---------------------------------------------------------------------------
# Package health (unit-tests the enrichment logic without subprocesses)
# ---------------------------------------------------------------------------

def _base_wired_status(tmp_path: Path) -> ModelStatus:
    return get_ace_status(_wired_settings(tmp_path))


def test_packages_unchecked_on_get_endpoint(client):
    c, _ = client
    body = c.get("/api/model-status").json()
    assert body["packages_checked"] is False
    assert body["packages_ok"] is None
    assert body["missing_packages"] == []


def test_enrich_status_with_all_packages_ok(tmp_path):
    status = _base_wired_status(tmp_path)
    fake_packages = {
        "ok": True,
        "packages": {"torch": "2.3.0", "torchaudio": "2.3.0", "transformers": "4.40.0",
                     "diffusers": "0.27.0", "accelerate": "0.29.0", "numpy": "1.26.0"},
        "missing_packages": [],
        "returncode": 0,
    }
    fake_diagnostic = {"ok": True, "info": {"torch": "2.3.0", "cuda_available": False, "cuda_device_count": 0}}
    enriched = enrich_status_with_packages(status, fake_packages, fake_diagnostic)

    assert enriched.packages_checked is True
    assert enriched.packages_ok is True
    assert enriched.missing_packages == []
    assert enriched.cuda_available is False  # populated from diagnostic
    assert enriched.cuda_ready is True  # cpu device in _wired_settings
    assert "ready" in enriched.user_message.lower() or "verified" in enriched.user_message.lower() or "cuda" in enriched.user_message.lower()


def test_enrich_status_packages_missing_shows_false(tmp_path):
    status = _base_wired_status(tmp_path)
    fake_packages = {
        "ok": False,
        "packages": {
            "torch": "missing: No module named 'torch'",
            "torchaudio": "missing: No module named 'torchaudio'",
            "transformers": "4.40.0",
            "diffusers": "missing: No module named 'diffusers'",
            "accelerate": "0.29.0",
            "numpy": "1.26.0",
        },
        "missing_packages": ["torch", "torchaudio", "diffusers"],
        "returncode": 0,
    }
    enriched = enrich_status_with_packages(status, fake_packages, None)

    assert enriched.packages_checked is True
    assert enriched.packages_ok is False
    assert "torch" in enriched.missing_packages
    assert "diffusers" in enriched.missing_packages
    # can_generate is unchanged (wiring-only check)
    assert enriched.can_generate is True
    # user_message must name the problem
    assert "torch" in enriched.user_message or "package" in enriched.user_message.lower()


def test_enrich_status_cuda_expected_but_unavailable(tmp_path):
    settings = _wired_settings(tmp_path)
    settings = settings.model_copy(update={"ace_device": "cuda"})
    status = get_ace_status(settings)
    assert status.cuda_expected is True

    fake_packages = {"ok": True, "packages": {}, "missing_packages": [], "returncode": 0}
    fake_diagnostic = {"ok": True, "info": {"torch": "2.3.0", "cuda_available": False, "cuda_device_count": 0}}
    enriched = enrich_status_with_packages(status, fake_packages, fake_diagnostic)

    assert enriched.cuda_available is False
    assert enriched.cuda_ready is False
    assert "cuda" in enriched.user_message.lower() or "gpu" in enriched.user_message.lower()


def test_enrich_preserves_original_status_immutably(tmp_path):
    status = _base_wired_status(tmp_path)
    fake_packages = {"ok": False, "packages": {}, "missing_packages": ["torch"], "returncode": 0}
    enriched = enrich_status_with_packages(status, fake_packages, None)

    # Original must not be mutated
    assert status.packages_checked is False
    assert status.packages_ok is None
    assert enriched.packages_checked is True


# ---------------------------------------------------------------------------
# user_message content
# ---------------------------------------------------------------------------

def test_user_message_when_ace_disabled(tmp_path):
    settings = Settings(DATA_DIR=tmp_path, ACE_ENABLED=False, ACE_ALLOW_FALLBACK=True)
    status = get_ace_status(settings)
    assert "disabled" in status.user_message.lower() or "false" in status.user_message.lower()
    assert "fallback" in status.user_message.lower()


def test_user_message_when_ace_enabled_wiring_ok(tmp_path):
    status = get_ace_status(_wired_settings(tmp_path))
    assert "test" in status.user_message.lower() or "verify" in status.user_message.lower()


# ---------------------------------------------------------------------------
# API: test endpoint returns enriched status
# ---------------------------------------------------------------------------

def test_model_status_test_endpoint_returns_packages_checked(client):
    c, _ = client
    res = c.post("/api/model-status/test")
    assert res.status_code == 200
    body = res.json()
    assert "status" in body
    assert body["status"]["packages_checked"] is True
    # packages_ok may be True or False depending on system python, but field must be present
    assert body["status"]["packages_ok"] is not None or body["status"]["packages_ok"] is None  # always present
    assert "missing_packages" in body["status"]


def test_model_status_test_endpoint_structure(client):
    c, _ = client
    body = c.post("/api/model-status/test").json()
    assert "diagnostic" in body
    assert "packages" in body
    assert "dry_run" in body
    assert "recommended_actions" in body
    assert "status" in body
    # The enriched status must carry the new fields
    s = body["status"]
    assert "wiring_ok" in s
    assert "cuda_ready" in s
    assert "first_real_generation_verified" in s
    assert "hf_cache_configured" in s
    assert "hf_cache_exists" in s
    assert "user_message" in s
