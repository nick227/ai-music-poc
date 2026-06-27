from tests.test_slices_api import _import_and_tag, _seed_categories


def test_media_list_includes_ready_audio_flag(client):
    c, _ = client
    categories = _seed_categories(client)
    genre = next(item for item in categories if item["dimension"] == "GENRE")
    tagged = _import_and_tag(client, filename="ready-flag.wav", category_id=genre["id"])

    listed = c.get("/api/media?limit=50").json()["media"]
    row = next(item for item in listed if item["id"] == tagged["id"])
    assert row["ready_audio"] is True

    detail = c.get(f"/api/media/{tagged['id']}").json()
    assert detail["ready_audio"] is True
