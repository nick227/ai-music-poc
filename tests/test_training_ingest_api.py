import time

from app.domain.models import RightsStatus, ReviewStatus
from app.storage.local_media_store import LocalMediaStore
from tests.test_slices_api import _create_concept, _import_and_tag, _seed_categories, wav_upload


def _wait_for_terminal_status(client, run_id: str, timeout_seconds: float = 2.0) -> dict:
    c, _ = client
    deadline = time.time() + timeout_seconds
    detail = c.get(f"/api/training/runs/{run_id}").json()
    while detail["status"] in {"QUEUED", "RUNNING"} and time.time() < deadline:
        time.sleep(0.02)
        detail = c.get(f"/api/training/runs/{run_id}").json()
    return detail


def _tagged_upload(client, *, filename: str = "ready-track.wav", mark_reviewed: bool = False) -> dict:
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    return _import_and_tag(
        client,
        filename=filename,
        category_id=genre["id"],
        mark_reviewed=mark_reviewed,
    )


def _concept_only_upload(client, *, filename: str = "concept-only.wav") -> dict:
    c, _ = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    concept = _create_concept(client, [genre["id"]])
    media = c.post("/api/media/import", files=[wav_upload(filename)]).json()["media"][0]
    c.put(
        f"/api/media/{media['id']}/assignments",
        json={
            "mark_reviewed": False,
            "categories": [],
            "concepts": [{"concept_id": concept["id"], "role": "TRAINING_CANDIDATE", "quality_score": 3, "fit_score": 3}],
        },
    )
    return c.get(f"/api/media/{media['id']}").json()


def test_ready_audio_lists_categorized_media(client):
    c, _ = client
    tagged = _tagged_upload(client)

    res = c.get("/api/training/ready-audio")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1
    assert any(item["id"] == tagged["id"] for item in body["items"])
    assert body["groups"]


def test_ready_audio_includes_concept_only_without_review(client):
    c, _ = client
    tagged = _concept_only_upload(client)

    body = c.get("/api/training/ready-audio").json()
    assert any(item["id"] == tagged["id"] for item in body["items"])


def test_ready_audio_excludes_rejected_and_do_not_train(client):
    c, data_dir = client
    tagged = _tagged_upload(client, filename="blocked-ready.wav")
    store = LocalMediaStore(data_dir / "media")
    asset = store.get(tagged["id"])
    store.save(asset.model_copy(update={"review_status": ReviewStatus.REJECTED}))

    body = c.get("/api/training/ready-audio").json()
    assert not any(item["id"] == tagged["id"] for item in body["items"])

    tagged2 = _tagged_upload(client, filename="dnt-ready.wav")
    asset2 = store.get(tagged2["id"])
    store.save(asset2.model_copy(update={"rights_status": RightsStatus.DO_NOT_TRAIN}))
    body2 = c.get("/api/training/ready-audio").json()
    assert not any(item["id"] == tagged2["id"] for item in body2["items"])


def test_create_package_auto_trains_and_promotes_style_version(client):
    c, data_dir = client
    tagged = _tagged_upload(client)

    create = c.post("/api/training/packages", json={"config_preset": "calibration"})
    assert create.status_code == 200
    body = create.json()
    assert body["package"]["track_count"] == 1
    assert body["package"]["download_url"].endswith("/package")
    run = body["run"]
    assert run["status"] == "QUEUED"

    detail = _wait_for_terminal_status(client, run["id"])
    assert detail["status"] == "SUCCEEDED"
    assert detail["style_version_id"] is not None

    media = c.get(f"/api/media/{tagged['id']}").json()
    assert media["ingestion_status"] == "INGESTED"

    ready = c.get("/api/training/ready-audio").json()
    assert any(item["id"] == tagged["id"] for item in ready["items"])

    packages = c.get("/api/training/packages").json()["packages"]
    assert any(item["id"] == body["package"]["id"] for item in packages)


def test_create_package_empty_ready_audio_rejected(client):
    c, _ = client
    res = c.post("/api/training/packages", json={})
    assert res.status_code == 422
    assert "ready audio" in res.json()["message"].lower()


def test_ready_audio_orders_by_role_when_concept_selected(client):
    c, _ = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    concept = _create_concept(client, [genre["id"]])

    gold = _import_and_tag(client, filename="gold.wav", category_id=genre["id"], role="GOLD_REFERENCE")
    ref = _import_and_tag(client, filename="ref.wav", category_id=genre["id"], role="REFERENCE")
    c.put(
        f"/api/media/{gold['id']}/assignments",
        json={
            "mark_reviewed": False,
            "categories": [{"category_id": genre["id"], "role": "GOLD_REFERENCE", "quality_score": 5, "fit_score": 5, "reviewed": False}],
            "concepts": [{"concept_id": concept["id"], "role": "GOLD_REFERENCE", "quality_score": 5, "fit_score": 5}],
        },
    )
    c.put(
        f"/api/media/{ref['id']}/assignments",
        json={
            "mark_reviewed": False,
            "categories": [{"category_id": genre["id"], "role": "REFERENCE", "quality_score": 5, "fit_score": 5, "reviewed": False}],
            "concepts": [{"concept_id": concept["id"], "role": "REFERENCE", "quality_score": 5, "fit_score": 5}],
        },
    )

    body = c.get(f"/api/training/ready-audio?concept_id={concept['id']}").json()
    ids = [item["id"] for item in body["items"]]
    assert ids.index(gold["id"]) < ids.index(ref["id"])


def test_generate_with_style_version_sets_version_details(client):
    c, _ = client
    tagged = _tagged_upload(client, filename="style-gen.wav")
    create = c.post("/api/training/packages", json={}).json()["run"]
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
