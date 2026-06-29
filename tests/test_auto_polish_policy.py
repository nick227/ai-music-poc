from app.domain.models import GenerationResult
from app.services.generation_service import should_auto_polish


def test_skip_auto_polish_for_procedural_draft():
    result = GenerationResult(
        file_name="x.wav",
        duration_seconds=10,
        sample_rate=44100,
        generator_name="procedural-v3",
        metadata={"engine": "procedural-v3.32", "render_route": "draft-parametric"},
    )
    assert should_auto_polish(result) is False


def test_auto_polish_for_ace_render():
    result = GenerationResult(
        file_name="x.wav",
        duration_seconds=10,
        sample_rate=44100,
        generator_name="ace-step-command",
        metadata={"render_route": "final-neural", "render_backend": "ace-step-command"},
    )
    assert should_auto_polish(result) is True


def test_regression_draft_job_does_not_run_auto_polish(client, monkeypatch):
    polish_calls: list[object] = []

    def _fake_polish(path):
        polish_calls.append(path)
        return {"status": "success", "chain_used": "test"}

    monkeypatch.setattr("app.services.generation_service.auto_polish", _fake_polish)
    api_client, _ = client
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
    assert polish_calls == []
    assert job["status"] == "SUCCEEDED"
    assert "postprocess" not in (job.get("result") or {}).get("metadata", {})
