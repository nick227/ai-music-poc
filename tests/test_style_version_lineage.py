from pathlib import Path

from app.domain.training import TrainingRun
from app.services.style_version_service import StyleVersionService
from app.storage.style_version_store import StyleVersionStore


def test_style_version_copies_training_run_model_lineage(tmp_path: Path):
    run = TrainingRun(
        name="ACE turbo run",
        dataset_slice_id="slice_123",
        backend="ACE_STEP",
        base_model_id="ace-step-turbo",
        base_model_name="ACE-Step v1.5 Turbo",
        training_mode="lora",
        artifact_type="lora",
        config_preset="calibration",
        artifact_path="training_runs/train_123/artifacts/ace_output/final",
    )

    service = StyleVersionService(StyleVersionStore(tmp_path / "style_versions"))
    version = service.create_from_run(run, "Dark disco")

    assert version.training_run_id == run.id
    assert version.dataset_slice_id == "slice_123"
    assert version.base_model_id == "ace-step-turbo"
    assert version.base_model_name == "ACE-Step v1.5 Turbo"
    assert version.training_mode == "lora"
    assert version.artifact_type == "lora"
