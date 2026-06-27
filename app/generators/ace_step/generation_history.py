from __future__ import annotations

import json
from pathlib import Path


def _is_verified_ace_record(payload: dict) -> bool:
    if payload.get("generator") != "ace-step-command":
        return False
    settings = payload.get("settings") or {}
    if settings.get("backend") != "external-command":
        return False
    if settings.get("fallback_reason"):
        return False
    audio = settings.get("audio") or {}
    return bool(audio.get("file_size_bytes", 0) > 0)


def find_verified_ace_generation(metadata_dir: Path, scan_limit: int = 100) -> dict | None:
    """Return the most recent metadata proof of a real ACE subprocess generation."""
    if not metadata_dir.exists():
        return None
    candidates: list[tuple[str, dict]] = []
    for path in sorted(metadata_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if len(candidates) >= scan_limit:
            break
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if _is_verified_ace_record(payload):
            candidates.append((path.stem, payload))
    if not candidates:
        return None
    job_id, payload = candidates[0]
    settings = payload.get("settings") or {}
    audio = settings.get("audio") or {}
    return {
        "job_id": job_id,
        "verified_at": payload.get("created_at"),
        "duration_seconds": payload.get("duration_seconds"),
        "output_file": payload.get("output_file"),
        "engine": settings.get("engine"),
        "device": settings.get("device"),
        "ace_elapsed_seconds": settings.get("ace_elapsed_seconds"),
        "audio_channels": audio.get("channels"),
        "audio_sample_rate": audio.get("sample_rate"),
        "file_size_bytes": audio.get("file_size_bytes"),
    }
