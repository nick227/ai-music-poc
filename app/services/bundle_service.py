from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from app.domain.models import JobRecord
from app.storage.local_file_store import LocalFileStore
from app.storage.log_store import LogStore
from app.storage.metadata_store import MetadataStore


class BundleService:
    def __init__(self, file_store: LocalFileStore, metadata_store: MetadataStore, log_store: LogStore) -> None:
        self.file_store = file_store
        self.metadata_store = metadata_store
        self.log_store = log_store

    def build_manifest(self, job: JobRecord) -> dict[str, object]:
        if not job.result:
            raise RuntimeError("Job has no result to bundle")
        stem_name = (job.result.metadata or {}).get("vocal_stem_file")
        req = job.request
        return {
            "job_id": job.id,
            "title": req.title,
            "files": {
                "song": "song.wav",
                "vocal_stem": "vocal_stem.wav" if stem_name else None,
                "metadata": "metadata.json",
                "prompt": "prompt.txt",
                "lyrics": "lyrics.txt" if req.include_lyrics_in_bundle else None,
                "log": "job.log",
            },
            "generation": {
                "generator": req.generator,
                "mode": req.mode,
                "quality": req.quality,
                "duration_seconds": req.duration_seconds,
                "seed": req.seed,
                "bpm": req.bpm,
                "key": req.key,
                "singing_voice": req.singing_voice,
                "vocal_intensity": req.vocal_intensity,
                "vocal_style": req.vocal_style,
                "structure": req.structure,
            },
            "result": {
                "engine": (job.result.metadata or {}).get("engine"),
                "backend": (job.result.metadata or {}).get("backend"),
                "sample_rate": job.result.sample_rate,
            },
        }

    def create_bundle(self, job: JobRecord) -> Path:
        if not job.result:
            raise RuntimeError("Job has no result to bundle")
        tmp = Path(tempfile.gettempdir()) / f"{job.id}-bundle.zip"
        wav_path = self.file_store.path_for_file_name(job.result.file_name)
        metadata_path = self.metadata_store.path_for_job(job.id)
        log_path = self.log_store.path_for_job(job.id)
        manifest = self.build_manifest(job)
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if wav_path.exists():
                zf.write(wav_path, "song.wav")
            stem_name = (job.result.metadata or {}).get("vocal_stem_file")
            if stem_name:
                stem_path = self.file_store.path_for_file_name(stem_name)
                if stem_path.exists():
                    zf.write(stem_path, "vocal_stem.wav")
            zf.writestr("bundle.json", json.dumps(manifest, indent=2))
            if metadata_path.exists():
                zf.write(metadata_path, "metadata.json")
            else:
                zf.writestr("metadata.json", json.dumps(job.model_dump(mode="json"), indent=2))
            zf.writestr("prompt.txt", job.request.prompt)
            if job.request.include_lyrics_in_bundle:
                zf.writestr("lyrics.txt", job.request.lyrics)
            if log_path.exists():
                zf.write(log_path, "job.log")
        return tmp
