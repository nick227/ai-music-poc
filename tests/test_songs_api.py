from app.domain.enums import ReviewDecision
from app.domain.models import (
    GenerationRequest,
    GenerationResult,
    JobRecord,
    JobStatus,
    MediaAsset,
    MediaKind,
    MediaSource,
    ReviewStatus,
)
from app.storage.local_job_store import LocalJobStore
from app.storage.local_media_store import LocalMediaStore


def _seed_generated_song(data_dir):
    job = JobRecord(
        id="gen_song_api_1",
        status=JobStatus.SUCCEEDED,
        progress=1,
        message="Complete",
        request=GenerationRequest(
            title="Song API One",
            prompt="dark piano",
            lyrics="hello night",
            generator="fake",
            duration_seconds=10,
            seed=44,
        ),
        result=GenerationResult(
            file_name="gen_song_api_1.wav",
            duration_seconds=10,
            sample_rate=44100,
            generator_name="fake",
            metadata={"backend": "fake-backend", "engine": "fake-v1"},
        ),
        media_asset_id="media_gen_song_api_1",
        version_details={
            "generationId": "gen_song_api_1",
            "backend": "fake-backend",
            "modelVersion": "fake-v1",
            "prompt": "dark piano",
            "lyrics": "hello night",
            "seed": 44,
            "durationSeconds": 10,
        },
    )
    LocalJobStore(data_dir / "jobs").save(job)

    media = MediaAsset(
        id="media_gen_song_api_1",
        title="Song API One",
        kind=MediaKind.GENERATED_SONG,
        source=MediaSource.GENERATION,
        file_path="outputs/gen_song_api_1.wav",
        duration_seconds=10,
        sample_rate=44100,
        channels=2,
        generation_id=job.id,
        version_details=job.version_details,
    )
    LocalMediaStore(data_dir / "media").save(media)
    return media


def test_list_songs_returns_generated_songs_with_generation_metadata(client):
    c, data_dir = client
    media = _seed_generated_song(data_dir)
    LocalMediaStore(data_dir / "media").save(
        MediaAsset(
            id="media_upload_1",
            title="Upload",
            kind=MediaKind.UPLOAD,
            source=MediaSource.USER_IMPORT,
        )
    )

    res = c.get("/api/songs")

    assert res.status_code == 200
    body = res.json()
    assert list(body.keys()) == ["songs"]
    assert len(body["songs"]) == 1
    song = body["songs"][0]
    assert song["id"] == media.id
    assert song["kind"] == "GENERATED_SONG"
    assert song["review_status"] == "NEEDS_REVIEW"
    assert song["audio_url"] == f"/api/media/{media.id}/audio"
    assert song["version_details"]["backend"] == "fake-backend"
    assert song["version_details"]["model_version"] == "fake-v1"
    assert song["generation"]["id"] == "gen_song_api_1"
    assert song["generation"]["status"] == "SUCCEEDED"
    assert song["generation"]["output_path"] == "outputs/gen_song_api_1.wav"
    assert song["generation"]["prompt"] == "dark piano"
    assert song["generation"]["seed"] == 44


def test_get_song_returns_detail_for_generated_song(client):
    c, data_dir = client
    media = _seed_generated_song(data_dir)

    res = c.get(f"/api/songs/{media.id}")

    assert res.status_code == 200
    song = res.json()
    assert song["id"] == media.id
    assert song["media_asset_id"] == media.id
    assert song["file_path"] == "outputs/gen_song_api_1.wav"
    assert song["audio_url"] == f"/api/media/{media.id}/audio"
    assert song["duration_seconds"] == 10
    assert song["sample_rate"] == 44100
    assert song["channels"] == 2
    assert song["generation_id"] == "gen_song_api_1"
    assert song["generation"]["backend"] == "fake-backend"
    assert song["generation"]["model_version"] == "fake-v1"
    assert song["version_details"]["model_version"] == "fake-v1"


def test_get_song_rejects_non_generated_media(client):
    c, data_dir = client
    LocalMediaStore(data_dir / "media").save(
        MediaAsset(
            id="media_upload_1",
            title="Upload",
            kind=MediaKind.UPLOAD,
            source=MediaSource.USER_IMPORT,
        )
    )

    res = c.get("/api/songs/media_upload_1")

    assert res.status_code == 404


def test_review_song_keeper_marks_reviewed(client):
    c, data_dir = client
    media = _seed_generated_song(data_dir)

    res = c.post(
        f"/api/songs/{media.id}/review",
        json={"decision": "KEEPER", "overall_score": 5, "notes": "strong chorus"},
    )

    assert res.status_code == 200
    song = res.json()
    assert song["review_status"] == "REVIEWED"
    assert song["review_decision"] == "KEEPER"
    assert song["review_score"] == 5
    assert song["review_notes"] == "strong chorus"


def test_review_song_reject_marks_rejected(client):
    c, data_dir = client
    media = _seed_generated_song(data_dir)

    res = c.post(
        f"/api/songs/{media.id}/review",
        json={"decision": "REJECT", "overall_score": 2},
    )

    assert res.status_code == 200
    song = res.json()
    assert song["review_status"] == "REJECTED"
    assert song["review_decision"] == "REJECT"
    assert song["review_score"] == 2


def test_list_songs_filters_by_review_status(client):
    c, data_dir = client
    media = _seed_generated_song(data_dir)
    reviewed = MediaAsset(
        id="media_gen_reviewed",
        title="Reviewed Song",
        kind=MediaKind.GENERATED_SONG,
        source=MediaSource.GENERATION,
        review_status=ReviewStatus.REVIEWED,
        review_decision=ReviewDecision.KEEPER,
    )
    LocalMediaStore(data_dir / "media").save(reviewed)

    needs = c.get("/api/songs", params={"review_status": "NEEDS_REVIEW"}).json()["songs"]
    reviewed_rows = c.get("/api/songs", params={"review_status": "REVIEWED"}).json()["songs"]

    assert len(needs) == 1
    assert needs[0]["id"] == media.id
    assert len(reviewed_rows) == 1
    assert reviewed_rows[0]["id"] == reviewed.id


def test_list_songs_filters_by_style_version_id(client):
    c, data_dir = client
    style_version_id = "style_abc123"
    other_style_id = "style_xyz789"

    styled = MediaAsset(
        id="media_styled_1",
        title="Styled Song",
        kind=MediaKind.GENERATED_SONG,
        source=MediaSource.GENERATION,
        version_details={"styleVersionId": style_version_id, "prompt": "dark piano"},
    )
    other = MediaAsset(
        id="media_styled_2",
        title="Other Style Song",
        kind=MediaKind.GENERATED_SONG,
        source=MediaSource.GENERATION,
        version_details={"styleVersionId": other_style_id, "prompt": "bright guitar"},
    )
    untyled = MediaAsset(
        id="media_no_style",
        title="Base Song",
        kind=MediaKind.GENERATED_SONG,
        source=MediaSource.GENERATION,
        version_details={"prompt": "ambient pad"},
    )
    store = LocalMediaStore(data_dir / "media")
    store.save(styled)
    store.save(other)
    store.save(untyled)

    filtered = c.get("/api/songs", params={"style_version_id": style_version_id}).json()["songs"]
    assert len(filtered) == 1
    assert filtered[0]["id"] == styled.id

    all_songs = c.get("/api/songs", params={"limit": 100}).json()["songs"]
    assert len(all_songs) == 3
