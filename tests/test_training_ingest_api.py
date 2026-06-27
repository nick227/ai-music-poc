import time

from tests.test_slices_api import _import_and_tag, _seed_categories


def _wait_for_terminal_status(client, run_id: str, timeout_seconds: float = 2.0) -> dict:
    c, _ = client
    deadline = time.time() + timeout_seconds
    detail = c.get(f"/api/training/runs/{run_id}").json()
    while detail["status"] in {"QUEUED", "RUNNING"} and time.time() < deadline:
        time.sleep(0.02)
        detail = c.get(f"/api/training/runs/{run_id}").json()
    return detail


def _tagged_upload(client, *, filename: str = "inbox-track.wav", mark_reviewed: bool = False) -> dict:
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    return _import_and_tag(
        client,
        filename=filename,
        category_id=genre["id"],
        mark_reviewed=mark_reviewed,
    )


def test_ingestion_queue_lists_tagged_media(client):
    c, _ = client
    tagged = _tagged_upload(client)

    res = c.get("/api/training/queue")
    assert res.status_code == 200
    body = res.json()
    assert any(item["id"] == tagged["id"] for item in body["queue"])
    assert body["queue"][0]["category_count"] >= 1


def test_ingest_auto_slice_marks_media_and_promotes_style_version(client):
    c, data_dir = client
    tagged = _tagged_upload(client)

    create = c.post("/api/training/ingest", json={"config_preset": "calibration"})
    assert create.status_code == 200
    run = create.json()["run"]
    assert run["status"] == "QUEUED"

    detail = _wait_for_terminal_status(client, run["id"])
    assert detail["status"] == "SUCCEEDED"
    assert detail["style_version_id"] is not None
    assert detail["artifact_path"]

    media = c.get(f"/api/media/{tagged['id']}").json()
    assert media["ingestion_status"] == "INGESTED"
    assert media["last_training_run_id"] == run["id"]
    assert media["ingested_at"] is not None

    queue = c.get("/api/training/queue").json()
    assert not any(item["id"] == tagged["id"] for item in queue["queue"])
    assert any(item["id"] == tagged["id"] for item in queue["ingested"])

    styles = c.get("/api/style-versions").json()["style_versions"]
    assert any(item["id"] == detail["style_version_id"] for item in styles)


def test_ingest_empty_queue_rejected(client):
    c, _ = client
    res = c.post("/api/training/ingest", json={})
    assert res.status_code == 422
    assert "queue" in res.json()["message"].lower()


def test_generate_with_style_version_sets_version_details(client):
    c, _ = client
    tagged = _tagged_upload(client, filename="style-gen.wav")
    create = c.post("/api/training/ingest", json={}).json()["run"]
    detail = _wait_for_terminal_status(client, create["id"])
    style_id = detail["style_version_id"]

    gen = c.post(
        "/api/generate",
        json={
            "title": "Styled song",
            "prompt": "dark cinematic vocal",
            "generator": "procedural-v3",
            "duration_seconds": 10,
            "style_version_id": style_id,
        },
    )
    assert gen.status_code == 200
    job_id = gen.json()["job_id"]

    deadline = time.time() + 3.0
    job = c.get(f"/api/jobs/{job_id}/status").json()
    while job["status"] in {"QUEUED", "RUNNING"} and time.time() < deadline:
        time.sleep(0.02)
        job = c.get(f"/api/jobs/{job_id}/status").json()
    assert job["status"] == "SUCCEEDED"

    songs = c.get("/api/songs").json()["songs"]
    song = next(item for item in songs if item["generation"]["id"] == job_id)
    assert song["version_details"]["style_version_id"] == style_id
    assert song["version_details"]["training_run_id"] == detail["id"]
