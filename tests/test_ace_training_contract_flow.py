from scripts.verify_ace_training_contract_flow import (
    ARTIFACT_TYPE,
    BASE_MODEL_NAME,
    OLD_WINDOWS_CACHE,
    TRAINING_MODE,
    verify_ace_training_contract_flow,
)


def test_phase_3_ace_training_contract_flow(monkeypatch, tmp_path):
    ace_root = tmp_path / "external" / "ACE-Step-1.5"
    ace_python = ace_root / ".venv" / "bin" / "python"
    checkpoint_root = ace_root / "checkpoints"
    ace_python.parent.mkdir(parents=True)
    ace_python.write_text("# fake python\n", encoding="utf-8")
    (ace_root / "train.py").write_text("# fake train\n", encoding="utf-8")
    (checkpoint_root / "acestep-v15-turbo").mkdir(parents=True)

    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ACE_STEP_DIR", str(ace_root))
    monkeypatch.setenv("ACE_PYTHON", str(ace_python))
    monkeypatch.setenv("ACE_MODEL_DIR", str(checkpoint_root))
    monkeypatch.setenv("ACE_TRAIN_CHECKPOINT_DIR", str(checkpoint_root))
    monkeypatch.setenv("ACE_DEVICE", "cpu")

    report = verify_ace_training_contract_flow()

    assert report["success"] is True
    assert report["base_model_name"] == BASE_MODEL_NAME
    assert report["training_mode"] == TRAINING_MODE
    assert report["artifact_type"] == ARTIFACT_TYPE
    assert report["ace_python"] == str(ace_python)
    assert report["checkpoint_root"] == str(checkpoint_root)
    assert all(report["validation_results"].values())
    assert report["preprocess_executed"] is False
    assert report["full_training_executed"] is False
    assert report["validation_results"]["frozen_manifest_immutable"] is True
    assert report["validation_results"]["command_uses_external_ace_python"] is True
    assert OLD_WINDOWS_CACHE not in " ".join(report["generated_command"]["preprocess"])
    assert OLD_WINDOWS_CACHE not in " ".join(report["generated_command"]["train"])
