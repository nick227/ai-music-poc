import pytest
from pathlib import Path

from app.core.config import get_settings
from app.core.ace_runtime import save_runtime_profile, AceRuntimeStatus


def test_ace_wiring_integration(client, monkeypatch):
    """End-to-end: aceRuntimeConfig from safe profile flows into job + media version_details."""
    test_client, data_dir = client

    settings = get_settings()
    settings.ace_enabled = True
    settings.ace_allow_fallback = False
    settings.ace_command_template = "bash -c \"cp benchmark_out.wav $output_path && echo '--device $device $prompt' > $output_path.cmd\""

    # Write a hardware profile with a recognisable safe config so we can verify
    # the values are pulled into aceRuntimeConfig on every generated song.
    profile_data = {
        "ace_usable": True,
        "checked_at": "2026-06-27T22:00:00Z",
        "user_message": "ACE is ready",
        "warnings": [],
        "hardware": {
            "detected_at": "2026-06-27T22:00:00Z",
            "safe_recommended_config": {
                "checkpoint": "turbo-test",
                "lm_model": "test-lm-7b",
                "batch_size": 1,
                "duration": 10,
                "inference_steps": 8,
                "offload_to_cpu": True,
                "device": "cuda:0",
                "description": "Safe tier",
            },
        },
    }
    save_runtime_profile(data_dir, AceRuntimeStatus.model_validate(profile_data))

    payload = {
        "title": "Test Song",
        "prompt": "integration test",
        "generator": "ace-step-command",
        "duration_seconds": 10,
        "quality": "draft",
    }

    resp = test_client.post("/api/generate", json=payload)
    assert resp.status_code == 200, f"generate failed: {resp.text}"
    job_id = resp.json().get("id") or resp.json().get("job_id")

    job_resp = test_client.get(f"/api/jobs/{job_id}")
    assert job_resp.status_code == 200
    job_data = job_resp.json()
    job = job_data["job"]

    assert job["status"] == "SUCCEEDED", f"Job failed: {job.get('error')}"

    # aceRuntimeConfig present in job version_details
    assert "version_details" in job
    assert "aceRuntimeConfig" in job["version_details"], (
        f"aceRuntimeConfig missing from job version_details: {job['version_details'].keys()}"
    )

    media_id = job.get("media_asset_id")
    assert media_id is not None
    media_resp = test_client.get(f"/api/songs/{media_id}")
    assert media_resp.status_code == 200
    media_data = media_resp.json()

    # aceRuntimeConfig present in media asset version_details
    assert "version_details" in media_data
    assert "aceRuntimeConfig" in media_data["version_details"]

    ace_cfg = media_data["version_details"]["aceRuntimeConfig"]

    # Fields sourced from the safe_recommended_config
    assert ace_cfg["checkpoint"] == "turbo-test"
    assert ace_cfg["lm_model"] == "test-lm-7b"
    assert ace_cfg["offload_to_cpu"] is True
    assert ace_cfg["device"] == "cuda:0"
    assert ace_cfg["config_tier"] == "safe_recommended"
    assert ace_cfg["runtime_profile_detected_at"] == "2026-06-27T22:00:00Z"

    # inference_steps comes from request quality (draft=8); batch_size is always 1
    assert ace_cfg["inference_steps"] == 8
    assert ace_cfg["batch_size"] == 1

    # Verify adapter injected --offload-to-cpu and --use-lm into the command
    command_preview = job["result"]["metadata"].get("command_preview", "")
    assert "--offload-to-cpu" in command_preview
    assert "--use-lm" in command_preview

    # --- Generation is blocked when ace_usable is False ---
    profile_data["ace_usable"] = False
    profile_data["user_message"] = "Not usable"
    save_runtime_profile(data_dir, AceRuntimeStatus.model_validate(profile_data))

    resp2 = test_client.post("/api/generate", json={
        "title": "Test Song 2",
        "prompt": "integration test fail",
        "generator": "ace-step-command",
        "duration_seconds": 10,
    })
    assert resp2.status_code == 200
    job_id2 = resp2.json().get("id") or resp2.json().get("job_id")

    job2 = test_client.get(f"/api/jobs/{job_id2}").json()["job"]
    assert job2["status"] == "FAILED"
    error_msg = job2.get("error") or ""
    assert "ACE-Step is not ready" in error_msg or "ACE runtime is not usable" in error_msg, (
        f"Unexpected error: {error_msg[:200]}"
    )
