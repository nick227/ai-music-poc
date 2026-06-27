from app.domain.models import ReviewStatus, RightsStatus
from app.storage.local_media_store import LocalMediaStore
from tests.test_slices_api import _import_and_tag, _seed_categories, wav_upload


def test_media_ready_audio_true_with_category(client):
    c, _ = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    tagged = _import_and_tag(client, filename="ready-flag.wav", category_id=genre["id"])

    listed = c.get("/api/media?limit=50").json()["media"]
    row = next(item for item in listed if item["id"] == tagged["id"])
    assert row["ready_audio"] is True

    detail = c.get(f"/api/media/{tagged['id']}").json()
    assert detail["ready_audio"] is True


def test_media_ready_audio_false_without_tags(client):
    c, _ = client
    media = c.post("/api/media/import", files=[wav_upload("untagged.wav")]).json()["media"][0]
    detail = c.get(f"/api/media/{media['id']}").json()
    assert detail["ready_audio"] is False


def test_media_ready_audio_false_when_rejected(client):
    c, data_dir = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    tagged = _import_and_tag(client, filename="rejected.wav", category_id=genre["id"])
    store = LocalMediaStore(data_dir / "media")
    asset = store.get(tagged["id"])
    store.save(asset.model_copy(update={"review_status": ReviewStatus.REJECTED}))

    detail = c.get(f"/api/media/{tagged['id']}").json()
    assert detail["ready_audio"] is False


def test_media_ready_audio_false_when_do_not_train(client):
    c, data_dir = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    tagged = _import_and_tag(client, filename="dnt.wav", category_id=genre["id"])
    store = LocalMediaStore(data_dir / "media")
    asset = store.get(tagged["id"])
    store.save(asset.model_copy(update={"rights_status": RightsStatus.DO_NOT_TRAIN}))

    detail = c.get(f"/api/media/{tagged['id']}").json()
    assert detail["ready_audio"] is False
