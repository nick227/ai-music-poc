from __future__ import annotations

from pathlib import Path

ACE_MODEL_VARIANT = "turbo"


def ace_checkpoint_dir(ace_step_dir: Path, override: Path | None = None) -> Path:
    if override is not None:
        return override.expanduser().resolve()
    return (ace_step_dir / "checkpoints").resolve()


def build_preprocess_command(
    *,
    ace_python: Path,
    checkpoint_dir: Path,
    audio_dir: Path,
    dataset_json: Path,
    tensor_output: Path,
    device: str = "auto",
) -> list[str]:
    """Verified preprocess entry: train_fixed module with --preprocess."""
    return [
        str(ace_python),
        "-m",
        "acestep.training_v2.cli.train_fixed",
        "--checkpoint-dir",
        str(checkpoint_dir),
        "--model-variant",
        ACE_MODEL_VARIANT,
        "--preprocess",
        "--audio-dir",
        str(audio_dir),
        "--dataset-json",
        str(dataset_json),
        "--tensor-output",
        str(tensor_output),
        "--device",
        device,
        "--yes",
    ]


def build_train_command(
    *,
    ace_python: Path,
    train_script: Path,
    checkpoint_dir: Path,
    dataset_dir: Path,
    output_dir: Path,
    epochs: int,
    rank: int,
    learning_rate: float,
    device: str = "auto",
) -> list[str]:
    """Verified training entry: train.py fixed with dataset-dir and output-dir."""
    return [
        str(ace_python),
        str(train_script),
        "--yes",
        "fixed",
        "--checkpoint-dir",
        str(checkpoint_dir),
        "--model-variant",
        ACE_MODEL_VARIANT,
        "--dataset-dir",
        str(dataset_dir),
        "--output-dir",
        str(output_dir),
        "--epochs",
        str(epochs),
        "--rank",
        str(rank),
        "--learning-rate",
        str(learning_rate),
        "--device",
        device,
    ]


def adapter_final_dir(artifacts_dir: Path) -> Path:
    return artifacts_dir / "ace_output" / "final"


def run_tensors_dir(run_dir: Path) -> Path:
    return run_dir / "tensors"


def run_artifacts_dir(run_dir: Path) -> Path:
    return run_dir / "artifacts"


def run_ace_output_dir(run_dir: Path) -> Path:
    return run_artifacts_dir(run_dir) / "ace_output"


def run_adapter_final_dir(run_dir: Path) -> Path:
    return run_ace_output_dir(run_dir) / "final"


def required_adapter_files(final_dir: Path) -> tuple[Path, Path]:
    return final_dir / "adapter_config.json", final_dir / "adapter_model.safetensors"


def preprocess_command_with_shim(base_command: list[str], project_root: Path) -> list[str]:
    """Swap ``-m acestep...train_fixed`` for the local shim entry script."""
    shim = (project_root / "scripts" / "ace_train_fixed_shim.py").resolve()
    if len(base_command) >= 3 and base_command[1:3] == ["-m", "acestep.training_v2.cli.train_fixed"]:
        return [base_command[0], str(shim), *base_command[3:]]
    return base_command


def train_command_with_shim(base_command: list[str], project_root: Path) -> list[str]:
    """Swap ``train.py`` for the local invoke shim (expanded path-safety root)."""
    shim = (project_root / "scripts" / "ace_train_invoke.py").resolve()
    if len(base_command) >= 2 and base_command[1].endswith("train.py"):
        return [base_command[0], str(shim), *base_command[2:]]
    return base_command


def adapter_artifacts_valid(final_dir: Path) -> bool:
    config_path, weights_path = required_adapter_files(final_dir)
    return config_path.is_file() and weights_path.is_file()
