from pathlib import Path

from app.audio.postprocess import auto_polish, should_auto_polish
from app.domain.models import GenerationResult


def test_skip_auto_polish_for_procedural_draft():
    assert should_auto_polish("procedural-v3", "draft") is False


def test_auto_polish_for_ace_render():
    assert should_auto_polish("ace-step-command", "balanced") is True


def test_skip_auto_polish_from_result_metadata():
    result = GenerationResult(
        file_name="x.wav",
        duration_seconds=10,
        sample_rate=44100,
        generator_name="procedural-v3",
        metadata={"engine": "procedural-v3.32", "render_route": "draft-parametric"},
    )
    assert should_auto_polish(result.generator_name, "draft") is False


def test_regression_draft_job_skips_polish_chain(client):
    api_client, tmp = client
    job_id = api_client.post(
        "/api/generate",
        json={
            "title": "Polish Skip",
            "prompt": "bright pop chorus hook",
            "lyrics": "Verse:\nhello world\nChorus:\nsing it now",
            "generator": "procedural-v3",
            "duration_seconds": 10,
            "quality": "draft",
            "mode": "song",
        },
    ).json()["job_id"]
    job = api_client.get(f"/api/jobs/{job_id}").json()["job"]
    assert job["status"] == "SUCCEEDED"
    postprocess = (job.get("result") or {}).get("metadata", {}).get("postprocess", {})
    assert postprocess.get("postprocess_skipped") is True
    wav_path = tmp / "outputs" / job["result"]["file_name"]
    assert wav_path.exists()
    raw_path = wav_path.with_name(f"{wav_path.stem}_raw{wav_path.suffix}")
    assert raw_path.exists()


def test_regression_skipped_polish_restores_playback_wav(tmp_path: Path):
    target = tmp_path / "test.wav"
    target.write_bytes(b"original-audio-bytes")

    metadata = auto_polish(target, "procedural-v3", "draft")

    assert metadata["postprocess_skipped"] is True
    assert target.exists()
    assert target.read_bytes() == b"original-audio-bytes"
    assert (tmp_path / "test_raw.wav").exists()
