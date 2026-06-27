from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.domain.training import TrainingRun


class TrainingRunStore:
    def __init__(self, runs_dir: Path) -> None:
        self.runs_dir = runs_dir
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def save(self, run: TrainingRun) -> None:
        directory = self.run_dir(run.id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "run.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(run.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)

    def get(self, run_id: str) -> Optional[TrainingRun]:
        path = self.run_dir(run_id) / "run.json"
        if not path.exists():
            return None
        return TrainingRun.model_validate_json(path.read_text(encoding="utf-8"))

    def list_all(self) -> list[TrainingRun]:
        records: list[TrainingRun] = []
        for directory in self.runs_dir.iterdir():
            if not directory.is_dir():
                continue
            path = directory / "run.json"
            if not path.exists():
                continue
            try:
                records.append(TrainingRun.model_validate_json(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        records.sort(key=lambda item: item.created_at, reverse=True)
        return records

    def write_config(self, run_id: str, config: dict) -> Path:
        directory = self.run_dir(run_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "config.json"
        path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        return path

    def logs_dir(self, run_id: str) -> Path:
        directory = self.run_dir(run_id) / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def artifacts_dir(self, run_id: str) -> Path:
        directory = self.run_dir(run_id) / "artifacts"
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def log_path(self, run_id: str) -> Path:
        return self.logs_dir(run_id) / "train.log"

    def append_log(self, run_id: str, message: str) -> None:
        from datetime import datetime, timezone

        path = self.log_path(run_id)
        stamp = datetime.now(timezone.utc).isoformat()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {message}\n")

    def read_log_tail(self, run_id: str, max_chars: int = 8000) -> str:
        path = self.log_path(run_id)
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[-max_chars:]

    def find_active_run(self) -> Optional[TrainingRun]:
        from app.domain.models import JobStatus

        for run in self.list_all():
            if run.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
                return run
        return None
