import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from app.core.config import get_settings
from app.generators.registry import create_default_registry
from app.generators.svs.adapter import SvsCommandGenerator
from app.generators.svs.health import get_svs_status


def test_registry_includes_svs_vocal_generator():
    registry = create_default_registry(get_settings())
    assert "svs-vocal" in registry.names()
    info = registry.get("svs-vocal").info()
    assert info.name == "svs-vocal"
    assert info.available is True


def test_svs_runner_mock_backend(tmp_path: Path):
    score_path = Path("tests/fixtures/svs_score/pop_chorus.json")
    output_path = tmp_path / "stem.wav"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/svs_runner.py",
            "--score",
            str(score_path),
            "--output",
            str(output_path),
            "--backend",
            "mock",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    assert output_path.exists()
    assert "ok" in completed.stdout


def test_svs_vocal_generator_vocal_demo_job(client):
    api_client, _tmp = client
    job_id = api_client.post(
        "/api/generate",
        json={
            "title": "SVS Vocal Demo",
            "prompt": "bright pop chorus hook",
            "lyrics": "Verse:\nhello world\nChorus:\nsing it now",
            "generator": "svs-vocal",
            "duration_seconds": 10,
            "quality": "draft",
            "mode": "vocal_demo",
        },
    ).json()["job_id"]
    job = api_client.get(f"/api/jobs/{job_id}").json()["job"]
    assert job["status"] == "SUCCEEDED"
    metadata = job["result"]["metadata"]
    assert metadata["svs_score_file"].endswith("_svs_score.json")
    assert metadata["vocal_plan_file"].endswith("_vocal_plan.json")
    assert metadata["vocal_stem_file"].endswith("_vocal_stem.wav")
    assert metadata["svs_score_version"] == 1
    assert metadata["vocal_backend"] in ("svs-command", "svs-mock-fallback")


def test_bundle_includes_svs_score_for_svs_vocal_job(client):
    api_client, _tmp = client
    job_id = api_client.post(
        "/api/generate",
        json={
            "title": "SVS Bundle",
            "prompt": "pop vocal demo",
            "lyrics": "Verse:\nline one\nChorus:\nline two",
            "generator": "svs-vocal",
            "duration_seconds": 10,
            "quality": "balanced",
            "mode": "vocal_demo",
        },
    ).json()["job_id"]
    res = api_client.get(f"/api/download/{job_id}/bundle")
    assert res.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    names = set(zf.namelist())
    assert "svs_score.json" in names
    manifest = json.loads(zf.read("bundle.json"))
    assert manifest["files"]["svs_score"] == "svs_score.json"
    assert manifest["result"]["svs_score_version"] == 1
    assert manifest["result"]["vocal_backend"] in ("svs-command", "svs-mock-fallback")


def test_svs_command_generator_requires_lyrics(tmp_path: Path):
    from app.domain.models import GenerationRequest
    from app.generators.procedural import ProceduralGenerator

    generator = SvsCommandGenerator(settings=get_settings(), fallback=ProceduralGenerator())
    request = GenerationRequest.model_validate(
        {
            "title": "No Lyrics",
            "prompt": "instrumental only",
            "lyrics": "",
            "duration_seconds": 10,
            "mode": "vocal_demo",
        }
    )
    try:
        generator.generate(request, tmp_path / "out.wav")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_svs_status_reports_script_path():
    status = get_svs_status(get_settings())
    assert "svs_script" in status
    assert status["svs_allow_fallback"] is True
