import json
from pathlib import Path

from app.core.config import Settings
from app.domain.training import TrainingRun
from app.domain.training_presets import resolve_training_preset
from app.training.ace_adapter import AceTrainingAdapter, AceTrainingCommandBuilder
from app.training.adapter import TrainingRequest


def _request(tmp_path: Path) -> TrainingRequest:
    run = TrainingRun(
        name="ACE dry run",
        dataset_slice_id="slice_abc",
        backend="ace-step-dry-run",
        config_preset="calibration",
        config=resolve_training_preset("calibration"),
    )
    run_dir = tmp_path / "training_runs" / run.id
    run_dir.mkdir(parents=True)
    package_path = tmp_path / "slice-package.zip"
    package_path.write_bytes(b"zip")
    config_path = run_dir / "config.json"
    config_path.write_text(json.dumps(run.config), encoding="utf-8")
    return TrainingRequest(
        run=run,
        package_path=package_path,
        run_dir=run_dir,
        config_path=config_path,
        log_path=run_dir / "logs" / "train.log",
        artifacts_dir=run_dir / "artifacts",
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        DATA_DIR=tmp_path,
        ACE_TRAIN_PYTHON=Path("python"),
        ACE_TRAIN_SCRIPT=Path("train.py"),
        ACE_MODEL_DIR=tmp_path / "models",
        ACE_DEVICE="cpu",
        ACE_TRAIN_COMMAND_TEMPLATE=(
            "$python $script --request-file $request_file --package $package_path "
            "--config $config_file --log $log_file --output-dir $output_dir "
            "--model-dir $model_dir --device $device --steps $steps --rank $rank "
            "--learning-rate $learning_rate --epochs $epochs"
        ),
    )


def test_ace_training_command_builder_renders_dry_run_files(tmp_path):
    request = _request(tmp_path)
    cmd = AceTrainingCommandBuilder(_settings(tmp_path)).build(request)

    assert cmd[:2] == ["python", "train.py"]
    assert str(request.package_path) in cmd
    assert str(request.config_path) in cmd
    assert str(request.artifacts_dir) in cmd
    assert "100" in cmd
    assert "8" in cmd

    request_file = request.run_dir / "ace_train_request.json"
    payload = json.loads(request_file.read_text(encoding="utf-8"))
    assert payload["run_id"] == request.run.id
    assert payload["dataset_slice_id"] == "slice_abc"
    assert payload["dry_run"] is True


def test_ace_training_adapter_records_command_without_artifact(tmp_path):
    request = _request(tmp_path)
    result = AceTrainingAdapter(_settings(tmp_path)).run(request)

    assert result.dry_run is True
    assert result.command is not None
    assert result.run.status == "SUCCEEDED"
    assert result.run.artifact_path is None

    command_path = request.run_dir / "ace_train_command.json"
    command_payload = json.loads(command_path.read_text(encoding="utf-8"))
    assert command_payload["dry_run"] is True
    assert command_payload["command"] == result.command
