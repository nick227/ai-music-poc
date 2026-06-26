import json
from pathlib import Path
from typing import List, Optional

from app.domain.models import JobRecord


class LocalJobStore:
    def __init__(self, job_dir: Path) -> None:
        self.job_dir = job_dir
        self.job_dir.mkdir(parents=True, exist_ok=True)

    def save(self, job: JobRecord) -> None:
        path = self.job_dir / f"{job.id}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)

    def get(self, job_id: str) -> Optional[JobRecord]:
        path = self.job_dir / f"{job_id}.json"
        if not path.exists():
            return None
        return JobRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def list_recent(self, limit: int = 25) -> List[JobRecord]:
        records: list[JobRecord] = []
        for path in self.job_dir.glob("*.json"):
            try:
                records.append(JobRecord.model_validate_json(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        records.sort(key=lambda job: job.created_at, reverse=True)
        return records[:limit]
