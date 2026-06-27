from __future__ import annotations

from app.core.config import Settings
from app.domain.models import JobStatus
from app.domain.slices import DatasetSlice
from app.domain.training import TrainingRun


def is_dry_run_backend(backend: str) -> bool:
    normalized = backend.strip().lower()
    return normalized in {"ace-step-dry-run", "ace_step_dry_run"}


def is_mock_backend(backend: str) -> bool:
    normalized = backend.strip().lower()
    return normalized in {"mock-training", "mock"}


def real_ace_training_enabled(settings: Settings) -> bool:
    return False


def describe_pipeline(settings: Settings, adapter_name: str) -> dict:
    dry_run = adapter_name == "ace-step-dry-run"
    adapter_label = "ACE dry-run" if dry_run else "Mock training"
    command_configured = bool(settings.ace_train_command_template.strip())
    return {
        "adapter": adapter_name,
        "adapter_label": adapter_label,
        "training_enabled": settings.training_enabled,
        "ace_training_enabled": real_ace_training_enabled(settings),
        "ace_command_configured": command_configured,
        "message": (
            "Real ACE training is not enabled. The ACE dry-run adapter renders a command file only."
            if dry_run
            else "Mock training runs locally and writes a placeholder artifact. Real ACE training is not enabled."
        ),
    }


def describe_package(record: DatasetSlice) -> dict:
    return {
        "status_label": "Training package ready",
        "download_ready": bool(record.frozen_media_ids),
    }


def describe_run(run: TrainingRun, settings: Settings) -> dict:
    artifact_produced = bool(run.artifact_path)
    dry_run = is_dry_run_backend(run.backend)
    ace_enabled = real_ace_training_enabled(settings)

    if run.status == JobStatus.QUEUED:
        status_label = "Training queued"
    elif run.status == JobStatus.RUNNING:
        status_label = "Rendering ACE command" if dry_run else "Mock training in progress"
    elif run.status == JobStatus.SUCCEEDED:
        if dry_run:
            status_label = "ACE command rendered · real training not enabled"
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
