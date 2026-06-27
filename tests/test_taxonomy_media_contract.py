import io
import struct
import wave
from pathlib import Path


def write_test_wav(path: Path, duration_seconds: float = 0.25, sample_rate: int = 44100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = int(sample_rate * duration_seconds)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = b"".join(struct.pack("<h", 12000) for _ in range(frame_count))
        handle.writeframes(frames)


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


def test_categories_seed_is_idempotent_and_includes_energy(client):
    c, _ = client

    first = c.get("/api/categories")
    second = c.get("/api/categories")

    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body == second_body
    assert len(first_body["categories"]) >= 13

    dimensions = {item["dimension"] for item in first_body["categories"]}
    assert "ENERGY" in dimensions
    energy_names = {item["name"] for item in first_body["categories"] if item["dimension"] == "ENERGY"}
    assert energy_names == {"Low", "High"}


def test_create_concept_links_categories(client):
    c, _ = client
    categories = c.get("/api/categories").json()["categories"]
    category_ids = [item["id"] for item in categories if item["dimension"] in {"GENRE", "MOOD", "ENERGY"}][:3]

    res = c.post(
        "/api/concepts",
        json={
            "name": "Dark Cinematic Piano Vocal",
            "category_ids": category_ids,
        },
    )

    assert res.status_code == 200
    concept = res.json()
    assert concept["name"] == "Dark Cinematic Piano Vocal"
    assert concept["coverage_state"] == "EMPTY"
    assert set(concept["category_ids"]) == set(category_ids)

    detail = c.get(f"/api/concepts/{concept['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == concept["id"]


def test_media_import_creates_upload_asset(client, tmp_path):
    c, data_dir = client
    files = [wav_upload("night-piano.wav")]

    res = c.post("/api/media/import", files=files)

    assert res.status_code == 200
    body = res.json()
    assert len(body["media"]) == 1
    asset = body["media"][0]
    assert asset["kind"] == "UPLOAD"
    assert asset["source"] == "USER_IMPORT"
    assert asset["review_status"] == "NEEDS_REVIEW"
    assert asset["file_path"].startswith("uploads/media_")
    assert asset["file_path"].endswith(".wav")
    assert asset["duration_seconds"] is not None
    assert (data_dir / asset["file_path"]).exists()


def test_media_import_accepts_multiple_files(client):
    c, _ = client
    files = [
        wav_upload("one.wav"),
        wav_upload("two.wav"),
    ]

    res = c.post("/api/media/import", files=files)

    assert res.status_code == 200
    assert len(res.json()["media"]) == 2


def test_assignment_upsert_and_nested_get(client):
    c, _ = client
    categories = c.get("/api/categories").json()["categories"]
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    energy = next(item for item in categories if item["dimension"] == "ENERGY" and item["slug"] == "low")

    concept = c.post(
        "/api/concepts",
        json={"name": "Baseline Concept", "category_ids": [genre["id"], energy["id"]]},
    ).json()

    import_res = c.post("/api/media/import", files=[wav_upload("assign-me.wav")])
    media_id = import_res.json()["media"][0]["id"]

    first = c.put(
        f"/api/media/{media_id}/assignments",
        json={
            "categories": [
                {
                    "category_id": genre["id"],
                    "quality_score": 4,
                    "fit_score": 5,
                    "role": "GOLD_REFERENCE",
                    "notes": "strong reference",
                    "reviewed": True,
                }
            ],
            "concepts": [
                {
                    "concept_id": concept["id"],
                    "quality_score": 4,
                    "fit_score": 4,
                    "role": "REFERENCE",
                }
            ],
        },
    )
    assert first.status_code == 200
    assert len(first.json()["category_assignments"]) == 1
    assert first.json()["category_assignments"][0]["role"] == "GOLD_REFERENCE"

    second = c.put(
        f"/api/media/{media_id}/assignments",
        json={
            "categories": [
                {
                    "category_id": genre["id"],
                    "quality_score": 5,
                    "fit_score": 5,
                    "role": "TRAINING_CANDIDATE",
                    "notes": "updated",
                }
            ],
            "concepts": [],
        },
    )
    assert second.status_code == 200
    assignments = second.json()["category_assignments"]
    assert len(assignments) == 1
    assert assignments[0]["quality_score"] == 5
    assert assignments[0]["role"] == "TRAINING_CANDIDATE"
    assert assignments[0]["notes"] == "updated"

    detail = c.get(f"/api/media/{media_id}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert len(detail_body["category_assignments"]) == 1
    assert len(detail_body["concept_assignments"]) == 1
    assert detail_body["category_assignments"][0]["category_id"] == genre["id"]


def test_list_media_filters_review_status(client):
    c, data_dir = client
    c.post("/api/media/import", files=[wav_upload("inbox.wav")])

    res = c.get("/api/media", params={"review_status": "NEEDS_REVIEW", "kind": "UPLOAD"})
    assert res.status_code == 200
    media = res.json()["media"]
    assert len(media) == 1
    assert media[0]["review_status"] == "NEEDS_REVIEW"
