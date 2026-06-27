from pathlib import Path


def ensure_app_dirs(data_dir: Path) -> None:
    for child in ("jobs", "outputs", "media", "logs", "tmp", "uploads", "slices", "training_runs", "taxonomy/categories", "taxonomy/concepts", "taxonomy/assignments"):
        (data_dir / child).mkdir(parents=True, exist_ok=True)


def safe_child_path(base_dir: Path, filename: str) -> Path:
    base = base_dir.resolve()
    path = (base / filename).resolve()
    if base not in path.parents and path != base:
        raise ValueError("Unsafe path outside base directory")
    return path
