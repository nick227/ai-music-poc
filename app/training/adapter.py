from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.domain.training import TrainingRun


@dataclass(frozen=True)
class TrainingRequest:
    run: TrainingRun
    package_path: Path
    run_dir: Path
    config_path: Path
    log_path: Path
    artifacts_dir: Path


@dataclass(frozen=True)
class TrainingAdapterResult:
    run: TrainingRun
    command: list[str] | None = None
    dry_run: bool = False


class TrainingAdapter(Protocol):
    name: str
    supports_lora: bool

    def run(self, request: TrainingRequest) -> TrainingAdapterResult:
        """Execute or simulate a training run behind the Studio training flow."""
