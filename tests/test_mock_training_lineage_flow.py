from scripts.verify_mock_training_lineage_flow import (
    ARTIFACT_TYPE,
    BASE_MODEL_NAME,
    TRAINING_MODE,
    verify_mock_training_lineage_flow,
)


def test_phase_2_mock_training_lineage_flow(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    report = verify_mock_training_lineage_flow()

    assert report["success"] is True
    assert report["dataset"]["status"] == "READY"
    assert report["dataset"]["immutable_after_mock_training"] is True
    assert report["training_run"]["status"] == "SUCCEEDED"
    assert report["training_run"]["dataset_slice_id"] == report["dataset"]["slice_id"]
    assert report["training_run"]["base_model_name"] == BASE_MODEL_NAME
    assert report["training_run"]["training_mode"] == TRAINING_MODE
    assert report["training_run"]["artifact_type"] == ARTIFACT_TYPE
    assert report["training_run"]["artifact_exists"] is True
    assert (tmp_path / report["training_run"]["artifact_path"]).is_file()
    assert report["model_version"]["training_run_id"] == report["training_run"]["id"]
    assert report["model_version"]["dataset_slice_id"] == report["dataset"]["slice_id"]
    assert report["model_version"]["base_model_name"] == BASE_MODEL_NAME
    assert report["model_version"]["training_mode"] == TRAINING_MODE
    assert report["model_version"]["artifact_type"] == ARTIFACT_TYPE
