from __future__ import annotations

from app.core.config import Settings
from app.domain.models import JobStatus
from app.domain.slices import DatasetSlice
from app.domain.training import TrainingRun


def is_dry_run_backend(backend: str) -> bool:
    normalized = backend.strip().lower()
    return normalized in {"ace-step-dry-run", "ace_step_dry_run", "ace_step_real_dry_run"}


def is_mock_backend(backend: str) -> bool:
    normalized = backend.strip().lower()
    return normalized in {"mock-training", "mock"}


def is_real_ace_backend(backend: str) -> bool:
    normalized = backend.strip().lower()
    return normalized in {"ace-step-real", "ace_step", "ace_step_real"}


def real_training_gates_open(settings: Settings, run_config: dict) -> tuple[bool, str]:
    if settings.training_adapter != "ace-step-real":
        return False, "TRAINING_ADAPTER is not ace-step-real"
    if not settings.ace_real_training_enabled:
        return False, "ACE_REAL_TRAINING_ENABLED is not true"
    if not run_config.get("confirm_real_training"):
        return False, "confirm_real_training is not true"
    return True, ""


def real_subprocess_allowed(settings: Settings, run_config: dict) -> tuple[bool, str]:
    allowed, reason = real_training_gates_open(settings, run_config)
    if not allowed:
        return allowed, reason
    if settings.ace_train_dry_run:
        return False, "ACE_TRAIN_DRY_RUN is true"
    return True, ""


def real_ace_training_enabled(settings: Settings) -> bool:
    return settings.training_adapter == "ace-step-real" and settings.ace_real_training_enabled


def describe_pipeline(settings: Settings, adapter_name: str) -> dict:
    if adapter_name == "ace-step-dry-run":
        adapter_label = "ACE dry-run"
        message = "Real ACE training is not enabled. The ACE dry-run adapter renders a command file only."
    elif adapter_name == "ace-step-real":
        adapter_label = "ACE turbo LoRA"
        if settings.ace_train_dry_run:
            message = "ACE real adapter selected; ACE_TRAIN_DRY_RUN=true so subprocess training is disabled."
        elif not settings.ace_real_training_enabled:
            message = "ACE real adapter selected; set ACE_REAL_TRAINING_ENABLED=true to allow subprocess training."
        else:
            message = ""
    else:
        adapter_label = "Mock training"
        message = "Mock training runs locally and writes a placeholder artifact."

    command_configured = bool(settings.ace_train_command_template.strip()) or adapter_name == "ace-step-real"
    return {
        "adapter": adapter_name,
        "adapter_label": adapter_label,
        "training_enabled": settings.training_enabled,
        "ace_training_enabled": real_ace_training_enabled(settings) and not settings.ace_train_dry_run,
        "ace_command_configured": command_configured,
        "message": message,
    }


def describe_package(record: DatasetSlice) -> dict:
    return {
        "status_label": "Training package ready",
        "download_ready": bool(record.frozen_media_ids),
    }


def describe_run(run: TrainingRun, settings: Settings) -> dict:
    artifact_produced = bool(run.artifact_path)
    dry_run = is_dry_run_backend(run.backend)
    ace_enabled = real_ace_training_enabled(settings) and not settings.ace_train_dry_run

    if run.status == JobStatus.QUEUED:
        status_label = "Training queued"
    elif run.status == JobStatus.RUNNING:
        if is_real_ace_backend(run.backend):
            status_label = "ACE turbo LoRA training in progress"
        elif dry_run:
            status_label = "Rendering ACE command"
        else:
            status_label = "Mock training in progress"
    elif run.status == JobStatus.SUCCEEDED:
        if dry_run:
            status_label = "ACE command rendered · subprocess not started"
        elif is_real_ace_backend(run.backend) and artifact_produced:
            status_label = "ACE training complete · adapter produced"
        elif is_real_ace_backend(run.backend):
            status_label = "ACE training complete · adapter missing"
        elif artifact_produced:
            status_label = "Mock training complete · artifact produced"
        else:
            status_label = "Training complete · no artifact"
    elif run.status == JobStatus.FAILED:
        status_label = "Training failed"
    elif run.status == JobStatus.CANCELLED:
        status_label = "Training cancelled"
    else:
        status_label = run.status.value.lower()

    return {
        "status_label": status_label,
        "artifact_produced": artifact_produced,
        "dry_run": dry_run,
        "ace_training_enabled": ace_enabled,
        "mock_training": is_mock_backend(run.backend),
        "style_version_created": bool(run.style_version_id),
    }
