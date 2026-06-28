from scripts.verify_fixture_dataset_flow import verify_fixture_dataset_flow


def test_phase_1_fixture_dataset_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    report = verify_fixture_dataset_flow()

    assert report["success"] is True
    assert report["ready_media_counts"]["bell"] == 12
    assert report["ready_media_counts"]["chimes"] == 12
    assert report["ready_media_counts"]["ocean"] == 12
    assert set(report["candidate_ids"]) == {"bell", "chimes", "ocean"}
    assert report["frozen_dataset"]["track_count"] == 12
    assert report["frozen_dataset"]["total_duration_seconds"] == 60.0
    assert report["frozen_dataset"]["immutable_after_regenerate"] is True
