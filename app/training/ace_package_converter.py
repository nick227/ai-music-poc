from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any


PACKAGE_ROOT = "training-package"
TRACKS_DIR = f"{PACKAGE_ROOT}/tracks"


def unpack_studio_package(package_path: Path, workspace_dir: Path) -> Path:
    """Unpack a Studio training package zip into *workspace_dir*."""
    workspace_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, "r") as zf:
        zf.extractall(workspace_dir)
    package_root = workspace_dir / PACKAGE_ROOT
    if not package_root.is_dir():
        raise ValueError(f"Package missing {PACKAGE_ROOT}/ directory")
    return package_root


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _first_genre(labels: dict[str, Any], annotation: dict[str, Any]) -> str:
    for item in labels.get("categories", []):
        if item.get("dimension") == "GENRE" and item.get("name"):
            return str(item["name"])
    tags = labels.get("tags") or annotation.get("tags") or []
    return str(tags[0]) if tags else ""


def _custom_tag(manifest: dict[str, Any], config: dict[str, Any]) -> str:
    for source in (config, manifest):
        tag = source.get("custom_tag")
        if isinstance(tag, str) and tag.strip():
            return tag.strip()
    concept_id = manifest.get("concept_id")
    if isinstance(concept_id, str) and concept_id.strip():
        return concept_id.strip()
    return ""


def build_ace_dataset(
    package_root: Path,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert unpacked Studio package tracks into ACE-compatible dataset JSON."""
    config = config or {}
    manifest = _read_json(package_root / "manifest.json")
    tracks_root = package_root / "tracks"
    if not tracks_root.is_dir():
        raise ValueError(f"Package missing {TRACKS_DIR}/ directory")

    custom_tag = _custom_tag(manifest, config)
    samples: list[dict[str, Any]] = []

    for track_dir in sorted(tracks_root.iterdir()):
        if not track_dir.is_dir():
            continue
        audio_path = track_dir / "audio.wav"
        if not audio_path.is_file():
            continue

        rel_audio = f"./tracks/{track_dir.name}/audio.wav"
        labels = _read_json(track_dir / "labels.json")
        annotation = _read_json(track_dir / "annotation.json")
        caption = _read_text(track_dir / "caption.txt") or annotation.get("caption") or track_dir.name
        lyrics = _read_text(track_dir / "lyrics.txt") or annotation.get("lyrics") or ""
        music = annotation.get("music") if isinstance(annotation.get("music"), dict) else {}

        bpm = music.get("bpm")
        keyscale = music.get("key") or music.get("keyscale") or ""
        timesignature = music.get("time_signature") or music.get("timesignature") or ""
        language = annotation.get("language") or config.get("language") or "en"
        is_instrumental = not bool(lyrics)

        sample: dict[str, Any] = {
            "id": track_dir.name,
            "audio_path": rel_audio,
            "filename": "audio.wav",
            "caption": caption,
            "genre": _first_genre(labels, annotation),
            "lyrics": lyrics or "[Instrumental]",
            "bpm": bpm,
            "keyscale": keyscale,
            "timesignature": str(timesignature) if timesignature else "",
            "language": language,
            "is_instrumental": is_instrumental,
            "custom_tag": custom_tag,
            "labeled": True,
        }
        tags = labels.get("tags")
        if isinstance(tags, list) and tags:
            sample["tags"] = tags
        samples.append(sample)

    if not samples:
        raise ValueError("No audio tracks found in Studio training package")

    dataset_name = str(manifest.get("name") or config.get("name") or "studio-training-package")
    metadata: dict[str, Any] = {
        "name": dataset_name,
        "custom_tag": custom_tag,
        "tag_position": config.get("tag_position", "prepend"),
        "genre_ratio": int(config.get("genre_ratio", 0)),
        "num_samples": len(samples),
        "all_instrumental": all(item.get("is_instrumental") for item in samples),
    }
    return {"metadata": metadata, "samples": samples}


def ensure_unique_audio_filenames(package_root: Path, payload: dict[str, Any]) -> None:
    """Symlink each track to a unique filename so ACE tensor outputs do not collide."""
    tracks_root = package_root / "tracks"
    for sample in payload.get("samples", []):
        track_id = sample.get("id")
        if not isinstance(track_id, str) or not track_id:
            continue
        track_dir = tracks_root / track_id
        src = track_dir / "audio.wav"
        if not src.is_file():
            continue
        unique_name = f"{track_id}.wav"
        unique_path = track_dir / unique_name
        if not unique_path.exists():
            unique_path.symlink_to("audio.wav")
        sample["audio_path"] = f"./tracks/{track_id}/{unique_name}"
        sample["filename"] = unique_name


def write_ace_dataset_json(
    package_root: Path,
    *,
    config: dict[str, Any] | None = None,
) -> Path:
    """Write ACE dataset.json beside the unpacked training-package root."""
    payload = build_ace_dataset(package_root, config=config)
    ensure_unique_audio_filenames(package_root, payload)
    path = package_root / "dataset.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
