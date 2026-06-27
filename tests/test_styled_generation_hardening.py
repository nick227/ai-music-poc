from __future__ import annotations

import pytest

from tests.test_training_ingest_api import _wait_for_terminal_status, _tagged_upload


def test_generate_rejects_lora_scale_without_style_version(client):
    c, _ = client
    response = c.post(
        "/api/generate",
        json={
            "title": "Bad scale",
            "prompt": "test prompt",
            "generator": "ace-step-command",
            "duration_seconds": 10,
            "lora_scale": 0.5,
        },
    )
    assert response.status_code == 422
    assert "lora_scale" in response.json()["message"]


def test_generate_rejects_style_version_with_fallback(client):
    c, _ = client
    tagged = _tagged_upload(client, filename="fallback-style.wav")
    create = c.post("/api/training/packages", json={}).json()["run"]
    detail = _wait_for_terminal_status(client, create["id"])
    style_id = detail["style_version_id"]

    response = c.post(
        "/api/generate",
        json={
            "title": "Styled with fallback",
            "prompt": "dark cinematic vocal",
            "generator": "ace-step-command",
            "duration_seconds": 10,
            "style_version_id": style_id,
            "allow_fallback": True,
        },
    )
    assert response.status_code == 422
    assert "allow_fallback" in response.json()["message"]


def test_style_version_detail_includes_load_path_and_songs(client):
    c, _ = client
    runs = c.get("/api/training/runs").json()["runs"]
    styled_run = next((run for run in runs if run.get("style_version_id")), None)
    if styled_run is None:
        pytest.skip("no style version in test data")
    style_id = styled_run["style_version_id"]
    detail = c.get(f"/api/style-versions/{style_id}").json()
    assert detail["id"] == style_id
    assert detail["load_path"]
    assert "generated_songs" in detail


def test_songs_compare_endpoint(client):
    c, _ = client
    songs = c.get("/api/songs?limit=100").json()["songs"]
    styled = next((song for song in songs if (song.get("version_details") or {}).get("style_version_id")), None)
    if styled is None:
        pytest.skip("no styled song in test data")
    vd = styled["version_details"]
    baseline = next(
        (
            song
            for song in songs
            if not (song.get("version_details") or {}).get("style_version_id")
            and (song.get("version_details") or {}).get("prompt") == vd.get("prompt")
        ),
        None,
    )
    if baseline is None:
        pytest.skip("no matching baseline song")
    compare = c.get(f"/api/songs/compare?baseline_id={baseline['id']}&styled_id={styled['id']}").json()
    assert compare["baseline"]["id"] == baseline["id"]
    assert compare["styled"]["id"] == styled["id"]
    assert compare["style_version_id"] == vd.get("style_version_id")
