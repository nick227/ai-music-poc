from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.domain.training import TrainingRun
from app.domain.training_presets import resolve_training_preset
from app.training.ace_package_converter import build_ace_dataset, unpack_studio_package, write_ace_dataset_json
from app.training.ace_real_adapter import AceRealTrainingAdapter
from app.training.ace_train_commands import (
    adapter_final_dir,
    build_preprocess_command,
    build_train_command,
)
from app.training.adapter import TrainingRequest


ACE_PYTHON = Path("/home/administrator/models/ACE-Step-1.5/.venv/bin/python")
ACE_STEP_DIR = Path("/home/administrator/models/ACE-Step-1.5")
CHECKPOINT_DIR = ACE_STEP_DIR / "checkpoints"
TRAIN_SCRIPT = ACE_STEP_DIR / "train.py"


def _write_studio_package(path: Path, media_id: str = "media_1") -> None:
    root = path.parent / "pkg_build"
    track = root / "training-package" / "tracks" / media_id
    track.mkdir(parents=True)
    (track / "audio.wav").write_bytes(b"RIFF----WAVE")
    (track / "caption.txt").write_text("Dreamy synthwave night drive", encoding="utf-8")
    (track / "lyrics.txt").write_text("[Instrumental]", encoding="utf-8")
    (track / "labels.json").write_text(
        json.dumps(
            {
                "media_id": media_id,
                "tags": ["synthwave", "concept_night"],
                "categories": [{"name": "Synthwave", "dimension": "GENRE"}],
            }
        ),
        encoding="utf-8",
    )
    (track / "annotation.json").write_text(
        json.dumps(
            {
                "caption": "Dreamy synthwave night drive",
                "language": "en",
                "music": {"bpm": 118, "key": "A minor", "time_signature": "4"},
            }
        ),
        encoding="utf-8",
    )
    (root / "training-package" / "manifest.json").write_text(
        json.dumps({"name": "Night Drive", "concept_id": "concept_night"}),
        encoding="utf-8",
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in root.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(root).as_posix())


def _training_request(tmp_path: Path, *, confirm: bool = True) -> TrainingRequest:
    config = resolve_training_preset("calibration")
    if confirm:
        config["confirm_real_training"] = True
    run = TrainingRun(
        name="ACE real",
        dataset_slice_id="slice_abc",
        backend="ace-step-real",
        config_preset="calibration",
        config=config,
    )
    run_dir = tmp_path / "training_runs" / run.id
    run_dir.mkdir(parents=True)
    package_path = tmp_path / "slice-package.zip"
    _write_studio_package(package_path)
    config_path = run_dir / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)
    return TrainingRequest(
        run=run,
        package_path=package_path,
        run_dir=run_dir,
        config_path=config_path,
        log_path=run_dir / "logs" / "train.log",
        artifacts_dir=artifacts_dir,
    )


def _real_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "DATA_DIR": tmp_path,
        "TRAINING_ADAPTER": "ace-step-real",
        "ACE_REAL_TRAINING_ENABLED": True,
        "ACE_TRAIN_DRY_RUN": False,
        "ACE_STEP_DIR": ACE_STEP_DIR,
        "ACE_TRAIN_PYTHON": ACE_PYTHON,
        "ACE_TRAIN_SCRIPT": tmp_path.parent / "scripts" / "ace_train_runner.py"
        if (tmp_path.parent / "scripts" / "ace_train_runner.py").exists()
        else Path(__file__).resolve().parents[1] / "scripts" / "ace_train_runner.py",
        "ACE_TRAIN_CHECKPOINT_DIR": CHECKPOINT_DIR,
        "ACE_DEVICE": "cpu",
    }
    values.update(overrides)
    return Settings(**values)


def test_package_converter_emits_valid_ace_dataset_json(tmp_path):
    package_path = tmp_path / "package.zip"
    _write_studio_package(package_path)
    workspace = tmp_path / "workspace"
    package_root = unpack_studio_package(package_path, workspace)
    dataset_path = write_ace_dataset_json(package_root, config={"language": "en"})
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))

    assert payload["metadata"]["custom_tag"] == "concept_night"
    assert len(payload["samples"]) == 1
    sample = payload["samples"][0]
    assert sample["audio_path"] == "./tracks/media_1/audio.wav"
    assert sample["caption"] == "Dreamy synthwave night drive"
    assert sample["lyrics"] == "[Instrumental]"
    assert sample["bpm"] == 118
    assert sample["keyscale"] == "A minor"
    assert sample["timesignature"] == "4"
    assert sample["language"] == "en"
    assert sample["genre"] == "Synthwave"
    assert sample["custom_tag"] == "concept_night"


def test_preprocess_command_uses_verified_module_entry(tmp_path):
    cmd = build_preprocess_command(
        ace_python=ACE_PYTHON,
        checkpoint_dir=CHECKPOINT_DIR,
        audio_dir=tmp_path / "training-package",
        dataset_json=tmp_path / "training-package" / "dataset.json",
        tensor_output=tmp_path / "tensors",
        device="cpu",
    )
    assert cmd[0] == str(ACE_PYTHON)
    assert cmd[1:3] == ["-m", "acestep.training_v2.cli.train_fixed"]
    assert "--preprocess" in cmd
    assert "--model-variant" in cmd and cmd[cmd.index("--model-variant") + 1] == "turbo"
    assert cmd[cmd.index("--checkpoint-dir") + 1] == str(CHECKPOINT_DIR)


def test_train_command_uses_train_py_fixed_with_dataset_and_output_dirs(tmp_path):
    cmd = build_train_command(
        ace_python=ACE_PYTHON,
        train_script=TRAIN_SCRIPT,
        checkpoint_dir=CHECKPOINT_DIR,
        dataset_dir=tmp_path / "tensors",
        output_dir=tmp_path / "ace_output",
        epochs=1,
        rank=8,
        learning_rate=1e-4,
        device="cpu",
    )
    assert cmd[0] == str(ACE_PYTHON)
    assert cmd[1] == str(TRAIN_SCRIPT)
    assert cmd[2] == "fixed"
    assert cmd[cmd.index("--dataset-dir") + 1] == str(tmp_path / "tensors")
    assert cmd[cmd.index("--output-dir") + 1] == str(tmp_path / "ace_output")
    assert cmd[cmd.index("--model-variant") + 1] == "turbo"


@pytest.mark.parametrize(
    "settings_kwargs,config_confirm,error_fragment",
    [
        ({"TRAINING_ADAPTER": "mock-training"}, True, "TRAINING_ADAPTER"),
        ({"ACE_REAL_TRAINING_ENABLED": False}, True, "ACE_REAL_TRAINING_ENABLED"),
        ({}, False, "confirm_real_training"),
    ],
)
def test_real_adapter_refuses_without_all_gates(tmp_path, settings_kwargs, config_confirm, error_fragment):
    request = _training_request(tmp_path, confirm=config_confirm)
    settings = _real_settings(tmp_path, **settings_kwargs)
    with pytest.raises(RuntimeError, match=error_fragment):
        AceRealTrainingAdapter(settings).run(request)


def test_real_adapter_dry_run_never_starts_subprocess(tmp_path):
    request = _training_request(tmp_path)
    settings = _real_settings(tmp_path, ACE_TRAIN_DRY_RUN=True)
    with patch("app.training.ace_real_adapter.subprocess.run") as run_mock:
        result = AceRealTrainingAdapter(settings).run(request)
    run_mock.assert_not_called()
    assert result.dry_run is True
    assert result.run.artifact_path is None
    command_path = request.run_dir / "ace_train_command.json"
    payload = json.loads(command_path.read_text(encoding="utf-8"))
    assert payload["preprocess_command"][1:3] == ["-m", "acestep.training_v2.cli.train_fixed"]
    assert payload["train_command"][2] == "fixed"
    assert "--dry-run" in result.command


def test_real_adapter_sets_artifact_path_only_when_final_adapter_files_exist(tmp_path):
    request = _training_request(tmp_path)
    settings = _real_settings(tmp_path)
    final_dir = adapter_final_dir(request.artifacts_dir)
    final_dir.mkdir(parents=True)
    (final_dir / "adapter_config.json").write_text('{"peft_type":"LORA"}', encoding="utf-8")
    (final_dir / "adapter_model.safetensors").write_bytes(b"weights")

    with patch.object(AceRealTrainingAdapter, "_invoke_runner", return_value=0):
        result = AceRealTrainingAdapter(settings).run(request)

    assert result.run.artifact_path is not None
    assert result.run.artifact_path.endswith("artifacts/ace_output/final")
    manifest = json.loads((request.artifacts_dir / "artifact_manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifact_type"] == "ADAPTER_DIR"
    assert manifest["artifact_path"] == "ace_output/final"
    assert manifest["load_path"] == str(final_dir.resolve())
    assert "adapter_config.json" in manifest["required_files"]
    assert "adapter_model.safetensors" in manifest["required_files"]


def test_real_adapter_leaves_artifact_path_none_when_final_files_missing(tmp_path):
    request = _training_request(tmp_path)
    settings = _real_settings(tmp_path)
    with patch.object(AceRealTrainingAdapter, "_invoke_runner", return_value=0):
        result = AceRealTrainingAdapter(settings).run(request)
    assert result.run.artifact_path is None
    assert not (request.artifacts_dir / "artifact_manifest.json").exists()


def test_build_ace_dataset_requires_tracks(tmp_path):
    package_root = tmp_path / "training-package"
    (package_root / "tracks").mkdir(parents=True)
    with pytest.raises(ValueError, match="No audio tracks"):
        build_ace_dataset(package_root)
