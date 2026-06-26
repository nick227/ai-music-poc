from app.services.lyrics_service import format_lyrics


def test_format_lyrics_splits_verse_chorus():
    raw = "I saw your shadow in the blue light dancing where the city ends hold the night a little tighter before the morning breaks again"
    formatted = format_lyrics(raw, "verse_chorus")
    assert "Verse:" in formatted
    assert "Chorus:" in formatted
    assert formatted.count("\n") >= 3


def test_format_lyrics_respects_markers():
    raw = "Verse: hello world\nChorus: sing it loud"
    formatted = format_lyrics(raw, "auto")
    assert "Verse:" in formatted
    assert "hello world" in formatted
    assert "Chorus:" in formatted
    assert "sing it loud" in formatted


def test_format_lyrics_api(client):
    c, _ = client
    res = c.post("/api/format-lyrics", json={"lyrics": "one two three four five six seven eight nine ten", "structure": "verse_chorus"})
    assert res.status_code == 200
    body = res.json()
    assert body["section_count"] >= 2
    assert "Verse:" in body["formatted"]
