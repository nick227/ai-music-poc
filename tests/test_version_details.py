from app.domain.version_details import normalize_version_details


def test_normalize_version_details_maps_legacy_camel_case():
    raw = {
        "generationId": "gen_1",
        "modelVersion": "ace-v1",
        "targetCategoryIds": ["cat_genre_pop"],
        "settings": {"vocalStyle": "intimate", "quality": "high"},
    }
    normalized = normalize_version_details(raw)
    assert normalized["generation_id"] == "gen_1"
    assert normalized["model_version"] == "ace-v1"
    assert normalized["target_category_ids"] == ["cat_genre_pop"]
    assert normalized["settings"]["vocal_style"] == "intimate"
    assert normalized["settings"]["quality"] == "high"
