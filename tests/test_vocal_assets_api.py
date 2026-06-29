import io
import json
import zipfile


def test_vocal_download_url_when_stem_exists(client):
    c, _ = client
    job_id = c.post(
        "/api/generate",
        json={
            "title": "Stem Test",
            "prompt": "pop hook with clear vocal",
            "lyrics": "Verse:\nhello world\nChorus:\nsing it now",
            "generator": "procedural-v3",
            "duration_seconds": 10,
            "quality": "high",
            "mode": "vocal_demo",
            "singing_voice": "female",
            "vocal_intensity": 0.8,
        },
    ).json()["job_id"]
    status = c.get(f"/api/jobs/{job_id}").json()
    assert status["vocal_download_url"] == f"/api/download/{job_id}/vocal"
    res = c.get(f"/api/download/{job_id}/vocal")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("audio/")


def test_vocal_download_missing_for_draft(client):
    c, _ = client
    job_id = c.post(
        "/api/generate",
        json={
            "title": "No Stem",
            "prompt": "dark disco",
            "lyrics": "one two three",
            "generator": "procedural-v3",
            "duration_seconds": 10,
            "quality": "draft",
        },
    ).json()["job_id"]
    status = c.get(f"/api/jobs/{job_id}").json()
    assert status["vocal_download_url"] is None
    assert c.get(f"/api/download/{job_id}/vocal").status_code == 404


def test_bundle_includes_manifest_and_stem(client):
    c, _ = client
    job_id = c.post(
        "/api/generate",
        json={
            "title": "Bundle Manifest",
            "prompt": "pop vocal demo",
            "lyrics": "Verse:\nline one\nChorus:\nline two",
            "generator": "procedural-v3",
            "duration_seconds": 10,
            "quality": "balanced",
            "mode": "vocal_demo",
        },
    ).json()["job_id"]
    res = c.get(f"/api/download/{job_id}/bundle")
    assert res.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(res.content))
    names = set(zf.namelist())
    assert "bundle.json" in names
    assert "song.wav" in names
    assert "vocal_stem.wav" in names
    manifest = json.loads(zf.read("bundle.json"))
    assert manifest["generation"]["singing_voice"] == "auto"
    assert manifest["files"]["vocal_stem"] == "vocal_stem.wav"
    assert "vocal_plan.json" in names
    assert manifest["files"]["vocal_plan"] == "vocal_plan.json"


def test_vocal_plan_url_when_plan_exists(client):
    c, _ = client
    job_id = c.post(
        "/api/generate",
        json={
            "title": "Plan Test",
            "prompt": "pop hook with clear vocal",
            "lyrics": "Verse:\nhello world\nChorus:\nsing it now",
            "generator": "procedural-v3",
            "duration_seconds": 10,
            "quality": "draft",
            "mode": "song",
        },
    ).json()["job_id"]
    status = c.get(f"/api/jobs/{job_id}").json()
    assert status["vocal_plan_url"] == f"/api/download/{job_id}/vocal-plan"
    plan = c.get(f"/api/download/{job_id}/vocal-plan").json()
    assert plan["version"] == 1
    syllables = sum(len(line["syllables"]) for section in plan["sections"] for line in section["lines"])
    assert syllables >= 2
