from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.paths import safe_child_path
from app.domain.models import GenerationResult, JobRecord


class MetadataStore:
    def __init__(self, output_dir: Path, settings: Settings) -> None:
        self.output_dir = output_dir
        self.settings = settings
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def path_for_job(self, job_id: str) -> Path:
        clean = "".join(ch for ch in job_id if ch.isalnum() or ch in ("-", "_"))
        return safe_child_path(self.output_dir, f"{clean}.json")

    def write(self, job: JobRecord, result: GenerationResult) -> Path:
        req = job.request
        payload: dict[str, Any] = {
            "job_id": job.id,
            "title": req.title,
            "generator": result.generator_name,
            "prompt": req.prompt,
            "lyrics_hash": hashlib.sha256(req.lyrics.encode("utf-8")).hexdigest() if req.lyrics else None,
            "duration_seconds": result.duration_seconds,
            "seed": req.seed,
            "bpm": req.bpm,
            "key": req.key,
            "mode": req.mode,
            "structure": req.structure,
            "quality": req.quality,
            "genre_tags": req.genre_tags,
            "mood_tags": req.mood_tags,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "output_file": result.file_name,
            "settings": result.metadata,
            "version_details": job.version_details,
            "versionDetailsJson": job.version_details,
        }
        if result.metadata.get("backend") == "external-command":
            payload["ace"] = {
                "backend": "external-command",
                "engine": result.metadata.get("engine"),
                "device": result.metadata.get("device"),
                "model_dir": result.metadata.get("model_dir"),
                "hf_cache_dir": result.metadata.get("hf_cache_dir"),
                "elapsed_seconds": result.metadata.get("ace_elapsed_seconds"),
                "audio": result.metadata.get("audio"),
            }
        if self.settings.save_full_lyrics:
            payload["lyrics"] = req.lyrics
        path = self.path_for_job(job.id)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path
