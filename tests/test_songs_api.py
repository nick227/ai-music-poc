from app.domain.models import (
    GenerationRequest,
    GenerationResult,
    JobRecord,
    JobStatus,
    MediaAsset,
    MediaKind,
    MediaSource,
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
    assert song["version_details"]["backend"] == "fake-backend"
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
    assert song["duration_seconds"] == 10
    assert song["sample_rate"] == 44100
    assert song["channels"] == 2
    assert song["generation_id"] == "gen_song_api_1"
    assert song["generation"]["backend"] == "fake-backend"
    assert song["generation"]["model_version"] == "fake-v1"
    assert song["version_details"]["modelVersion"] == "fake-v1"


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
