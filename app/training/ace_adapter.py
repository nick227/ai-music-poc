from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.core.command_template import render_command, safe_write_text
from app.core.config import Settings
from app.domain.models import JobStatus
from app.training.adapter import TrainingAdapterResult, TrainingRequest


class AceTrainingCommandBuilder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def prepare_files(self, request: TrainingRequest) -> dict[str, Path]:
        request_file = request.run_dir / "ace_train_request.json"
        payload = {
            "run_id": request.run.id,
            "dataset_slice_id": request.run.dataset_slice_id,
            "backend": "ACE_STEP",
            "config_preset": request.run.config_preset,
            "config": request.run.config,
            "artifacts_dir": str(request.artifacts_dir),
            "dry_run": True,
            "reinforcement_mode": request.run.reinforcement_mode,
            "parent_lora_path": request.run.parent_lora_path,
        }
        safe_write_text(request_file, json.dumps(payload, indent=2))
        return {"request_file": request_file}

    def build(self, request: TrainingRequest) -> list[str]:
        files = self.prepare_files(request)
        values = {
            "python": self.settings.ace_train_python,
            "script": self.settings.ace_train_script,
            "request_file": files["request_file"],
            "package_path": request.package_path,
            "run_dir": request.run_dir,
            "config_file": request.config_path,
            "log_file": request.log_path,
            "output_dir": request.artifacts_dir,
            "artifacts_dir": request.artifacts_dir,
            "model_dir": self.settings.ace_model_dir,
            "device": request.run.config.get("device") or self.settings.ace_device,
            "preset": request.run.config_preset,
            "steps": request.run.config.get("steps", ""),
            "rank": request.run.config.get("rank", ""),
            "learning_rate": request.run.config.get("learning_rate", ""),
            "epochs": request.run.config.get("epochs", ""),
            "parent_lora_path": request.run.parent_lora_path if request.run.reinforcement_mode == "enabled" else "",
        }
        return render_command(self.settings.ace_train_command_template, values)


class AceTrainingAdapter:
    name = "ace-step-dry-run"
    supports_lora = True

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.builder = AceTrainingCommandBuilder(settings)

    def run(self, request: TrainingRequest) -> TrainingAdapterResult:
        if not self.settings.ace_train_command_template.strip():
            raise RuntimeError("ACE_TRAIN_COMMAND_TEMPLATE is not configured")

        command = self.builder.build(request)
        command_path = request.run_dir / "ace_train_command.json"
        command_path.write_text(
            json.dumps(
                {
                    "dry_run": True,
                    "command": command,
                    "rendered_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        started = datetime.now(timezone.utc)
        run = request.run.model_copy(
            update={
                "backend": "ACE_STEP_DRY_RUN",
                "base_model_id": "ace-step",
                "base_model_name": "ACE-Step v1.5 Turbo",
                "training_mode": "lora",
                "artifact_type": "lora",
                "status": JobStatus.SUCCEEDED,
                "started_at": started,
                "finished_at": started,
                "updated_at": started,
                "artifact_path": None,
            }
        )
        return TrainingAdapterResult(run=run, command=command, dry_run=True)
