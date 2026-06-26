from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.core.paths import safe_child_path


class LogStore:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def path_for_job(self, job_id: str) -> Path:
        clean = "".join(ch for ch in job_id if ch.isalnum() or ch in ("-", "_"))
        return safe_child_path(self.log_dir, f"{clean}.log")

    def append(self, job_id: str, message: str) -> None:
        path = self.path_for_job(job_id)
        stamp = datetime.now(timezone.utc).isoformat()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{stamp}] {message}\n")

    def tail(self, job_id: str, max_chars: int = 4000) -> str:
        path = self.path_for_job(job_id)
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[-max_chars:]
