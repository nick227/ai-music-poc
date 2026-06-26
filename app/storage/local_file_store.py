from pathlib import Path

from app.core.paths import safe_child_path


class LocalFileStore:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def output_path_for_job(self, job_id: str, extension: str = "wav") -> Path:
        clean = "".join(ch for ch in job_id if ch.isalnum() or ch in ("-", "_"))
        return safe_child_path(self.output_dir, f"{clean}.{extension}")

    def path_for_file_name(self, file_name: str) -> Path:
        return safe_child_path(self.output_dir, file_name)
