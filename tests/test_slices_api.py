import io
import json
import struct
import wave
import zipfile
from pathlib import Path

from app.domain.models import RightsStatus
from app.storage.local_media_store import LocalMediaStore


def wav_upload(filename: str = "reference.wav", duration_seconds: float = 0.25) -> tuple[str, io.BytesIO, str]:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        sample_rate = 44100
        frame_count = int(sample_rate * duration_seconds)
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = b"".join(struct.pack("<h", 12000) for _ in range(frame_count))
        handle.writeframes(frames)
    buffer.seek(0)
    return ("files", (filename, buffer, "audio/wav"))


def _seed_categories(client):
    c, _ = client
    return c.get("/api/categories").json()["categories"]


def _import_and_tag(
    client,
    *,
    filename: str,
    category_id: str,
    role: str = "GOLD_REFERENCE",
    quality_score: int = 4,
    fit_score: int = 4,
    mark_reviewed: bool = True,
    rights_status: str | None = None,
) -> dict:
    c, data_dir = client
    media = c.post("/api/media/import", files=[wav_upload(filename)]).json()["media"][0]
    c.put(
        f"/api/media/{media['id']}/assignments",
        json={
            "mark_reviewed": mark_reviewed,
            "categories": [
                {
                    "category_id": category_id,
                    "role": role,
                    "quality_score": quality_score,
                    "fit_score": fit_score,
                    "reviewed": mark_reviewed,
                }
            ],
            "concepts": [],
        },
    )
    if rights_status is not None:
        asset = LocalMediaStore(data_dir / "media").get(media["id"])
        LocalMediaStore(data_dir / "media").save(
            asset.model_copy(update={"rights_status": RightsStatus(rights_status)})
        )
    return c.get(f"/api/media/{media['id']}").json()


def _create_concept(client, category_ids: list[str]) -> dict:
    c, _ = client
    return c.post(
        "/api/concepts",
        json={"name": "Dark Piano Vocal", "category_ids": category_ids},
    ).json()


def test_preview_filters_by_review_status_and_rights(client):
    c, _ = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")

    ready = _import_and_tag(client, filename="ready.wav", category_id=genre["id"], rights_status="CONFIRMED")
    _import_and_tag(
        client,
        filename="needs-review.wav",
        category_id=genre["id"],
        mark_reviewed=False,
        rights_status="CONFIRMED",
    )
    _import_and_tag(client, filename="blocked.wav", category_id=genre["id"], rights_status="DO_NOT_TRAIN")

    res = c.get(
        "/api/slices/preview",
        params={
            "review_status": "REVIEWED",
            "rights_status": "CONFIRMED",
            "category_ids": genre["id"],
            "roles": "GOLD_REFERENCE",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 1
    assert body["media"][0]["id"] == ready["id"]


def test_preview_filters_by_min_quality_and_fit(client):
    c, _ = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")

    strong = _import_and_tag(
        client,
        filename="strong.wav",
        category_id=genre["id"],
        quality_score=5,
        fit_score=5,
        rights_status="CONFIRMED",
    )
    _import_and_tag(
        client,
        filename="weak.wav",
        category_id=genre["id"],
        quality_score=2,
        fit_score=2,
        rights_status="CONFIRMED",
    )

    res = c.get(
        "/api/slices/preview",
        params={
            "category_ids": genre["id"],
            "min_quality": 4,
            "min_fit": 4,
            "review_status": "REVIEWED",
            "rights_status": "CONFIRMED",
        },
    )
    assert res.status_code == 200
    ids = {item["id"] for item in res.json()["media"]}
    assert ids == {strong["id"]}


def test_preview_filters_by_concept(client):
    c, _ = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    mood = next(item for item in categories if item["dimension"] == "MOOD")
    concept = _create_concept(client, [genre["id"], mood["id"]])

    tagged = _import_and_tag(client, filename="concept-match.wav", category_id=genre["id"], rights_status="CONFIRMED")
    c.put(
        f"/api/media/{tagged['id']}/assignments",
        json={
            "categories": [{"category_id": genre["id"], "role": "GOLD_REFERENCE", "quality_score": 4, "fit_score": 4}],
            "concepts": [{"concept_id": concept["id"], "role": "GOLD_REFERENCE", "quality_score": 5, "fit_score": 5}],
        },
    )
    _import_and_tag(client, filename="no-concept.wav", category_id=genre["id"], rights_status="CONFIRMED")

    res = c.get(
        "/api/slices/preview",
        params={
            "concept_id": concept["id"],
            "review_status": "REVIEWED",
            "rights_status": "CONFIRMED",
        },
    )
    assert res.status_code == 200
    assert res.json()["count"] == 1
    assert res.json()["media"][0]["id"] == tagged["id"]


def test_create_slice_from_filter(client):
    c, _ = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    tagged = _import_and_tag(client, filename="slice-one.wav", category_id=genre["id"], rights_status="CONFIRMED")

    res = c.post(
        "/api/slices",
        json={
            "name": "Cinematic References",
            "filter": {
                "category_ids": [genre["id"]],
                "roles": ["GOLD_REFERENCE"],
                "review_status": "REVIEWED",
                "rights_status": "CONFIRMED",
                "min_quality": 3,
            },
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Cinematic References"
    assert body["status"] == "DRAFT"
    assert body["asset_count"] == 1
    assert body["media_ids"] == [tagged["id"]]


def test_update_slice_recomputes_members(client):
    c, _ = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    first = _import_and_tag(client, filename="first.wav", category_id=genre["id"], rights_status="CONFIRMED")
    created = c.post(
        "/api/slices",
        json={
            "name": "Draft Slice",
            "filter": {
                "category_ids": [genre["id"]],
                "review_status": "REVIEWED",
                "rights_status": "CONFIRMED",
            },
        },
    ).json()

    second = _import_and_tag(client, filename="second.wav", category_id=genre["id"], rights_status="CONFIRMED")
    updated = c.put(
        f"/api/slices/{created['id']}",
        json={"filter": {"category_ids": [genre["id"]], "review_status": "REVIEWED", "rights_status": "CONFIRMED"}},
    ).json()

    assert set(updated["media_ids"]) == {first["id"], second["id"]}
    assert updated["asset_count"] == 2


def test_freeze_writes_manifest_and_frozen_media_ids(client):
    c, data_dir = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    tagged = _import_and_tag(client, filename="freeze-me.wav", category_id=genre["id"], rights_status="CONFIRMED")
    created = c.post(
        "/api/slices",
        json={
            "name": "Freeze Slice",
            "media_ids": [tagged["id"]],
            "filter": {"category_ids": [genre["id"]]},
        },
    ).json()

    frozen = c.post(f"/api/slices/{created['id']}/freeze").json()
    assert frozen["status"] == "READY"
    assert frozen["frozen_media_ids"] == [tagged["id"]]
    assert frozen["frozen_at"] is not None

    manifest_path = data_dir / "slices" / created["id"] / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["media_ids"] == [tagged["id"]]
    assert manifest["track_count"] == 1

    audio_path = data_dir / "slices" / created["id"] / "audio" / f"{tagged['id']}.wav"
    assert audio_path.exists()


def test_freeze_is_idempotent(client):
    c, _ = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    tagged = _import_and_tag(client, filename="freeze-twice.wav", category_id=genre["id"], rights_status="CONFIRMED")
    created = c.post(
        "/api/slices",
        json={"name": "Idempotent", "media_ids": [tagged["id"]], "filter": {}},
    ).json()

    first = c.post(f"/api/slices/{created['id']}/freeze").json()
    second = c.post(f"/api/slices/{created['id']}/freeze").json()
    assert first == second


def test_package_download_requires_ready_slice(client):
    c, _ = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    tagged = _import_and_tag(client, filename="package-draft.wav", category_id=genre["id"], rights_status="CONFIRMED")
    created = c.post(
        "/api/slices",
        json={"name": "Draft Package", "media_ids": [tagged["id"]], "filter": {}},
    ).json()

    res = c.get(f"/api/slices/{created['id']}/package")
    assert res.status_code == 422


def test_package_download_contains_manifest_audio_and_labels(client):
    c, _ = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    tagged = _import_and_tag(client, filename="package-ready.wav", category_id=genre["id"], rights_status="CONFIRMED")
    created = c.post(
        "/api/slices",
        json={"name": "Ready Package", "media_ids": [tagged["id"]], "filter": {}},
    ).json()
    c.post(f"/api/slices/{created['id']}/freeze")

    res = c.get(f"/api/slices/{created['id']}/package")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(res.content))
    names = set(zf.namelist())
    assert "training-package/manifest.json" in names
    assert f"training-package/tracks/{tagged['id']}/audio.wav" in names
    assert f"training-package/tracks/{tagged['id']}/labels.json" in names
    assert f"training-package/tracks/{tagged['id']}/caption.txt" in names
    assert f"training-package/tracks/{tagged['id']}/annotation.json" in names
    assert "training-package/rights.json" in names
    assert "training-package/captions.csv" in names

    manifest = json.loads(zf.read("training-package/manifest.json"))
    assert manifest["slice_id"] == created["id"]
    assert manifest["media_ids"] == [tagged["id"]]

    labels = json.loads(zf.read(f"training-package/tracks/{tagged['id']}/labels.json"))
    assert labels["media_id"] == tagged["id"]
    assert labels["categories"]
    assert labels["tags"]

    caption = zf.read(f"training-package/tracks/{tagged['id']}/caption.txt").decode()
    assert caption

    annotation = json.loads(zf.read(f"training-package/tracks/{tagged['id']}/annotation.json"))
    assert annotation["media_id"] == tagged["id"]
    assert annotation["caption"] == caption
    assert annotation["taxonomy"]["categories"]
    assert annotation["signals"]["rights_status"] == "CONFIRMED"

    rights = json.loads(zf.read("training-package/rights.json"))
    assert rights[0]["rights_status"] == "CONFIRMED"


def test_list_and_get_slice(client):
    c, _ = client
    created = c.post("/api/slices", json={"name": "Listed Slice", "filter": {}, "media_ids": []}).json()
    listed = c.get("/api/slices").json()["slices"]
    assert any(item["id"] == created["id"] for item in listed)

    detail = c.get(f"/api/slices/{created['id']}").json()
    assert detail["id"] == created["id"]
    assert detail["name"] == "Listed Slice"
