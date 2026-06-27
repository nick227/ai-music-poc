from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import Settings
from app.domain.models import JobStatus
from app.domain.training_status import real_training_gates_open
from app.training.ace_train_commands import (
    adapter_artifacts_valid,
    adapter_final_dir,
    build_preprocess_command,
    build_train_command,
    required_adapter_files,
    run_adapter_final_dir,
    run_ace_output_dir,
    run_tensors_dir,
)
from app.training.adapter import TrainingAdapterResult, TrainingRequest


class AceRealTrainingAdapter:
    name = "ace-step-real"
    supports_lora = True

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(self, request: TrainingRequest) -> TrainingAdapterResult:
        allowed, reason = real_training_gates_open(self.settings, request.run.config)
        if not allowed:
            raise RuntimeError(f"Real ACE training refused: {reason}")

        command_payload = self._build_command_payload(request)
        command_path = request.run_dir / "ace_train_command.json"
        command_path.write_text(json.dumps(command_payload, indent=2), encoding="utf-8")

        dry_run = self.settings.ace_train_dry_run
        runner_cmd = self._runner_command(request, dry_run=dry_run)
        started = datetime.now(timezone.utc)

        if dry_run:
            run = request.run.model_copy(
                update={
                    "backend": "ACE_STEP_REAL_DRY_RUN",
                    "base_model_version": "ace-step-turbo",
                    "status": JobStatus.SUCCEEDED,
                    "started_at": started,
                    "finished_at": started,
                    "updated_at": started,
                    "artifact_path": None,
                }
            )
            return TrainingAdapterResult(run=run, command=runner_cmd, dry_run=True)

        run = request.run.model_copy(
            update={
                "backend": "ACE_STEP",
                "base_model_version": "ace-step-turbo",
                "status": JobStatus.RUNNING,
                "started_at": started,
                "updated_at": started,
            }
        )
        exit_code = self._invoke_runner(request, runner_cmd)
        finished = datetime.now(timezone.utc)
        if exit_code != 0:
            run = run.model_copy(
                update={
                    "status": JobStatus.FAILED,
                    "error": f"ace_train_runner exited with code {exit_code}",
                    "finished_at": finished,
                    "updated_at": finished,
                }
            )
            return TrainingAdapterResult(run=run, command=runner_cmd, dry_run=False)

        final_dir = run_adapter_final_dir(request.run_dir)
        artifact_path = self._write_artifact_manifest(request.artifacts_dir, final_dir)
        run = run.model_copy(
            update={
                "status": JobStatus.SUCCEEDED,
                "artifact_path": artifact_path,
                "finished_at": finished,
                "updated_at": finished,
                "error": None,
            }
        )
        return TrainingAdapterResult(run=run, command=runner_cmd, dry_run=False)

    def _build_command_payload(self, request: TrainingRequest) -> dict:
        ace_step_dir = self._ace_step_dir()
        ace_python = self.settings.ace_train_python.expanduser().resolve()
        train_script = (ace_step_dir / "train.py").resolve()
        checkpoint_dir = self._checkpoint_dir(ace_step_dir)
        workspace = request.run_dir / "workspace"
        package_root = workspace / "training-package"
        dataset_json = package_root / "dataset.json"
        tensor_dir = run_tensors_dir(request.run_dir)
        ace_output = run_ace_output_dir(request.run_dir)
        config = request.run.config

        preprocess = build_preprocess_command(
            ace_python=ace_python,
            checkpoint_dir=checkpoint_dir,
            audio_dir=package_root,
            dataset_json=dataset_json,
            tensor_output=tensor_dir,
            device=self.settings.ace_device,
        )
        train = build_train_command(
            ace_python=ace_python,
            train_script=train_script,
            checkpoint_dir=checkpoint_dir,
            dataset_dir=tensor_dir,
            output_dir=ace_output,
            epochs=int(config.get("epochs", 1)),
            rank=int(config.get("rank", 8)),
            learning_rate=float(config.get("learning_rate", 1e-4)),
            device=self.settings.ace_device,
        )
        return {
            "dry_run": self.settings.ace_train_dry_run,
            "model_variant": "turbo",
            "checkpoint_dir": str(checkpoint_dir),
            "preprocess_command": preprocess,
            "train_command": train,
            "artifact_final_dir": str(adapter_final_dir(request.artifacts_dir)),
            "rendered_at": datetime.now(timezone.utc).isoformat(),
        }

    def _runner_command(self, request: TrainingRequest, *, dry_run: bool) -> list[str]:
        ace_step_dir = self._ace_step_dir()
        cmd = [
            str(self.settings.ace_train_python.expanduser().resolve()),
            str(self.settings.ace_train_script.expanduser().resolve()),
            "--package",
            str(request.package_path),
            "--config",
            str(request.config_path),
            "--output-dir",
            str(request.run_dir),
            "--log",
            str(request.log_path),
            "--checkpoint-dir",
            str(self._checkpoint_dir(ace_step_dir)),
            "--device",
            self.settings.ace_device,
            "--ace-step-dir",
            str(ace_step_dir),
        ]
        if dry_run:
            cmd.append("--dry-run")
        return cmd

    def _invoke_runner(self, request: TrainingRequest, command: list[str]) -> int:
        request.log_path.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        ace_step_dir = self._ace_step_dir()
        env["ACE_STEP_DIR"] = str(ace_step_dir)
        with request.log_path.open("a", encoding="utf-8") as log_handle:
            log_handle.write(f"[runner] {' '.join(command)}\n")
            log_handle.flush()
            result = subprocess.run(
                command,
                cwd=str(ace_step_dir),
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                timeout=self.settings.ace_train_timeout_seconds,
                check=False,
            )
        return result.returncode

    def _write_artifact_manifest(self, artifacts_dir: Path, final_dir: Path) -> str | None:
        if not adapter_artifacts_valid(final_dir):
            return None

        config_path, weights_path = required_adapter_files(final_dir)
        rel_artifact = f"training_runs/{artifacts_dir.parent.name}/artifacts/ace_output/final"
        payload = {
            "artifact_type": "ADAPTER_DIR",
            "artifact_path": "ace_output/final",
            "load_path": str(final_dir.resolve()),
            "required_files": {
                "adapter_config.json": str(config_path.resolve()),
                "adapter_model.safetensors": str(weights_path.resolve()),
            },
            "model_variant": "turbo",
        }
        manifest_path = artifacts_dir / "artifact_manifest.json"
        manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return rel_artifact

    def _ace_step_dir(self) -> Path:
        if self.settings.ace_step_dir is not None:
            return self.settings.ace_step_dir.expanduser().resolve()
        return Path("/home/administrator/models/ACE-Step-1.5").resolve()

    def _checkpoint_dir(self, ace_step_dir: Path) -> Path:
        if self.settings.ace_train_checkpoint_dir is not None:
            return self.settings.ace_train_checkpoint_dir.expanduser().resolve()
        return (ace_step_dir / "checkpoints").resolve()
