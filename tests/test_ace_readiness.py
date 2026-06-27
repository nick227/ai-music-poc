from __future__ import annotations

import json
from pathlib import Path

from app.core.config import Settings
from app.domain.models import GenerationRequest, GenerationResult, JobRecord, JobStatus
from app.generators.ace_step.generation_history import find_verified_ace_generation
from app.storage.metadata_store import MetadataStore


def test_find_verified_ace_generation_ignores_fallback(tmp_path: Path):
    meta_dir = tmp_path / "outputs"
    meta_dir.mkdir()
    fallback = {
        "generator": "ace-step-command",
        "settings": {"backend": "procedural-fallback", "fallback_reason": "timeout"},
    }
    (meta_dir / "fallback.json").write_text(json.dumps(fallback), encoding="utf-8")

    real = {
        "job_id": "abc123",
        "generator": "ace-step-command",
        "created_at": "2026-06-27T00:00:00+00:00",
        "duration_seconds": 10,
        "output_file": "abc123.wav",
        "settings": {
            "backend": "external-command",
            "engine": "ace-step-command-v3.4",
            "device": "cuda",
            "ace_elapsed_seconds": 42.5,
            "audio": {"file_size_bytes": 882044, "channels": 2, "sample_rate": 44100},
        },
    }
    (meta_dir / "abc123.json").write_text(json.dumps(real), encoding="utf-8")

    proof = find_verified_ace_generation(meta_dir)
    assert proof is not None
    assert proof["job_id"] == "abc123"
    assert proof["file_size_bytes"] == 882044
    assert proof["engine"] == "ace-step-command-v3.4"


def test_metadata_store_adds_ace_summary_block(tmp_path: Path):
    settings = Settings(DATA_DIR=tmp_path, SAVE_FULL_LYRICS=False)
    store = MetadataStore(tmp_path / "outputs", settings)
    job = JobRecord(
        id="job1",
        status=JobStatus.SUCCEEDED,
        request=GenerationRequest(prompt="test", duration_seconds=10, generator="ace-step-command"),
        result=GenerationResult(
            file_name="job1.wav",
            duration_seconds=10,
            sample_rate=44100,
            generator_name="ace-step-command",
            metadata={
                "backend": "external-command",
                "engine": "ace-step-command-v3.4",
                "device": "cuda",
                "model_dir": "/cache/checkpoints",
                "ace_elapsed_seconds": 30.0,
                "audio": {"file_size_bytes": 1000, "channels": 2, "sample_rate": 44100},
            },
        ),
    )
    path = store.write(job, job.result)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["ace"]["backend"] == "external-command"
    assert payload["ace"]["audio"]["channels"] == 2
    assert payload["settings"]["backend"] == "external-command"


def test_ace_success_metadata_shape(tmp_path: Path):
    """External-command metadata must be API-serializable without nested command argv."""
    settings = Settings(
        DATA_DIR=tmp_path,
        ACE_ENABLED=True,
        ACE_SCRIPT=tmp_path / "runner.py",
        ACE_MODEL_DIR=tmp_path / "models",
        ACE_COMMAND_TEMPLATE="$python $script --output $output_path --prompt-file $prompt_file",
    )
    settings.ace_script.write_text("# stub")
    settings.ace_model_dir.mkdir()

    result = GenerationResult(
        file_name="out.wav",
        duration_seconds=10,
        sample_rate=44100,
        generator_name="ace-step-command",
        metadata={
            "engine": "ace-step-command-v3.4",
            "backend": "external-command",
            "device": "cuda",
            "command_preview": "python runner.py --output out.wav",
            "ace_returncode": 0,
            "audio": {"file_size_bytes": 5000, "channels": 2, "sample_rate": 44100},
        },
    )
    dumped = result.model_dump()
    assert "command" not in dumped["metadata"]
    assert dumped["metadata"]["backend"] == "external-command"


def test_model_status_reports_generation_proof(client, tmp_path):
    c, data_dir = client
    meta_dir = data_dir / "outputs"
    meta_dir.mkdir(exist_ok=True)
    proof = {
        "generator": "ace-step-command",
        "created_at": "2026-06-27T01:00:00+00:00",
        "duration_seconds": 10,
        "output_file": "proof.wav",
        "settings": {
            "backend": "external-command",
            "audio": {"file_size_bytes": 1234, "channels": 2, "sample_rate": 44100},
        },
    }
    (meta_dir / "proofjob.json").write_text(json.dumps(proof), encoding="utf-8")

    body = c.get("/api/model-status").json()
    assert body["first_real_generation_verified"] is True
    assert body["first_real_generation"]["job_id"] == "proofjob"
