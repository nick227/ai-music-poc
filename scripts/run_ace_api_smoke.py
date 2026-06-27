"""Poll POST /api/generate until ACE job completes; verify metadata and model-status."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.api import dependencies
from app.core.config import get_settings
from app.main import create_app


def main() -> int:
    load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    dependencies.get_job_service.cache_clear()
    dependencies.get_file_store.cache_clear()
    dependencies.get_log_store.cache_clear()
    dependencies.get_metadata_store.cache_clear()
    dependencies.get_bundle_service.cache_clear()
    dependencies.get_generation_service.cache_clear()
    dependencies.get_registry.cache_clear()

    settings = get_settings()
    if not settings.ace_enabled:
        print("ACE_ENABLED is false — set in .env before running this script.")
        return 2

    client = TestClient(create_app())
    payload = {
        "title": "Studio ACE API smoke",
        "prompt": "short dark disco test, simple beat, clear vocal demo",
        "lyrics": "Verse:\nAPI smoke test line\nChorus:\nMake a tiny song",
        "generator": "ace-step-command",
        "duration_seconds": 10,
        "seed": 4242,
        "quality": "draft",
        "allow_fallback": False,
    }
    print("POST /api/generate")
    created = client.post("/api/generate", json=payload)
    if created.status_code != 200:
        print(created.text)
        return created.status_code
    body = created.json()
    assert set(body.keys()) >= {"job_id", "status", "output_path"}
    assert body["output_path"] is None
    job_id = body["job_id"]
    print(f"job_id={job_id} status={body['status']}")

    deadline = time.time() + settings.ace_timeout_seconds
    while time.time() < deadline:
        poll = client.get(f"/api/jobs/{job_id}/status")
        if poll.status_code != 200:
            print(poll.text)
            return poll.status_code
        status_body = poll.json()
        status = status_body["status"]
        print(f"poll status={status} output_path={status_body.get('output_path')}")
        if status in ("SUCCEEDED", "FAILED", "TIMEOUT", "CANCELLED"):
            break
        time.sleep(2)
    else:
        print("Timed out waiting for job")
        return 1

    if status != "SUCCEEDED":
        detail = client.get(f"/api/jobs/{job_id}").json()
        print(json.dumps(detail, indent=2, default=str))
        return 1

    meta_path = settings.output_dir / f"{job_id}.json"
    if not meta_path.exists():
        print(f"Missing metadata: {meta_path}")
        return 1
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    print(f"metadata backend={meta.get('settings', {}).get('backend')} ace_block={meta.get('ace', {}).get('backend')}")
    if meta.get("settings", {}).get("backend") != "external-command":
        print("Expected external-command in metadata settings")
        return 1

    model_status = client.get("/api/model-status").json()
    print(f"first_real_generation_verified={model_status.get('first_real_generation_verified')}")
    if not model_status.get("first_real_generation_verified"):
        print(json.dumps(model_status, indent=2))
        return 1

    wav = settings.output_dir / f"{job_id}.wav"
    print(f"OK wav={wav} size={wav.stat().st_size if wav.exists() else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
