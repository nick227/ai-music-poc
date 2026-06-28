#!/usr/bin/env python3
"""Ingest Synthetic Dark Bell v1 clips into Studio media/category stores."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

from app.core.config import get_settings
from app.domain.enums import AssignmentRole, CategoryDimension, IngestionStatus
from app.domain.models import MediaAsset, MediaKind, MediaSource, ReviewStatus, RightsStatus
from app.domain.seeds import category_seed_id
from app.domain.taxonomy import MediaCategoryAssignment
from app.services.category_service import CategoryService
from app.storage.assignment_store import AssignmentStore
from app.storage.category_store import CategoryStore
from app.storage.local_media_store import LocalMediaStore

PACK_NAME = "dark-bell-v1"

# Categories for every clip in this pack
PACK_CATEGORY_SPECS: list[tuple[str, CategoryDimension]] = [
    ("Bell",      CategoryDimension.INSTRUMENT),
    ("Metallic",  CategoryDimension.PRODUCTION),
    ("Ambient",   CategoryDimension.GENRE),
    ("Sparse",    CategoryDimension.ARRANGEMENT),
    ("Dark",      CategoryDimension.MOOD),
    ("Synthetic", CategoryDimension.PRODUCTION),
]


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_wav(path: Path) -> dict:
    """Read WAV headers directly (no ffprobe dependency)."""
    with wave.open(str(path), "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        n_frames = wf.getnframes()
        duration = n_frames / sample_rate if sample_rate else 0.0
    return {
        "duration_seconds": round(duration, 4),
        "sample_rate": sample_rate,
        "channels": channels,
    }


def _resolve_category(service: CategoryService, name: str, dimension: CategoryDimension):
    slug = _slug(name)
    expected_id = category_seed_id(dimension, slug)
    existing = service.store.get(expected_id)
    if existing is not None:
        return existing
    for category in service.list(dimension=dimension, include_archived=False):
        if category.slug == slug:
            return category
    return service.create(name=name, dimension=dimension, slug=slug,
                          description=f"Synthetic Dark Bell v1 pack category: {name}")


def _find_existing_by_hash(media_store: LocalMediaStore, file_hash: str) -> MediaAsset | None:
    for asset in media_store.list_recent(limit=100_000):
        details = asset.version_details or {}
        if details.get("synthetic_sha256") == file_hash:
            return asset
    return None


def ingest_synthetic_pack(
    *,
    pack_dir: Path | None = None,
    metadata_path: Path | None = None,
) -> dict:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()

    pack_dir = pack_dir or (settings.data_dir / "synthetic_audio" / PACK_NAME)
    pack_dir = pack_dir.expanduser()
    if not pack_dir.is_absolute():
        pack_dir = (ROOT / pack_dir).resolve()

    meta_file = metadata_path or (pack_dir / "metadata.jsonl")
    if not meta_file.is_file():
        raise FileNotFoundError(f"metadata.jsonl not found at {meta_file} — run generate_synthetic_instrument_pack.py first")

    metadata_by_filename: dict[str, dict] = {}
    with meta_file.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                row = json.loads(line)
                fname = Path(row["file_path"]).name
                metadata_by_filename[fname] = row

    category_service = CategoryService(CategoryStore(settings.categories_dir))
    media_store = LocalMediaStore(settings.media_dir)
    assignment_store = AssignmentStore(settings.assignments_dir)

    categories = {}
    for name, dimension in PACK_CATEGORY_SPECS:
        cat = _resolve_category(category_service, name, dimension)
        categories[f"{dimension.value}:{name}"] = cat

    imported: list[dict] = []
    reused: list[dict] = []
    wav_files = sorted(pack_dir.glob("*.wav"))

    if not wav_files:
        raise RuntimeError(f"No WAV files found in {pack_dir}")

    for wav_path in wav_files:
        file_hash = _sha256(wav_path)
        probe = _probe_wav(wav_path)
        meta_row = metadata_by_filename.get(wav_path.name, {})

        relative_path = (
            wav_path.relative_to(settings.data_dir.resolve())
            if wav_path.is_relative_to(settings.data_dir.resolve())
            else wav_path
        )
        now = datetime.now(timezone.utc)
        asset = _find_existing_by_hash(media_store, file_hash)

        clip_index = meta_row.get("clip_index", wav_path.stem.rsplit("-", 1)[-1])
        title = f"Dark Bell v1 Clip {clip_index}"

        version_details = {
            "pack": PACK_NAME,
            "synthetic_sha256": file_hash,
            "synthetic_path": str(wav_path),
            "clip_index": clip_index,
            "caption": meta_row.get("caption", ""),
            "tags": meta_row.get("tags", []),
            "seed": meta_row.get("seed"),
            "synthesis_params": meta_row.get("synthesis_params", {}),
        }

        if asset is None:
            asset = MediaAsset(
                title=title,
                kind=MediaKind.UPLOAD,
                source=MediaSource.USER_IMPORT,
                file_path=relative_path.as_posix(),
                duration_seconds=probe["duration_seconds"],
                sample_rate=probe["sample_rate"],
                channels=probe["channels"],
                review_status=ReviewStatus.REVIEWED,
                rights_status=RightsStatus.CONFIRMED,
                version_details=version_details,
                updated_at=now,
            )
            media_store.save(asset)
            imported.append({"media_id": asset.id, "file": wav_path.name, "sha256": file_hash})
        else:
            asset = asset.model_copy(update={
                "file_path": relative_path.as_posix(),
                "duration_seconds": probe["duration_seconds"],
                "sample_rate": probe["sample_rate"],
                "channels": probe["channels"],
                "review_status": ReviewStatus.REVIEWED,
                "rights_status": RightsStatus.CONFIRMED,
                "version_details": version_details,
                "updated_at": now,
            })
            media_store.save(asset)
            reused.append({"media_id": asset.id, "file": wav_path.name, "sha256": file_hash})

        for _key, category in categories.items():
            assignment_store.upsert_category_assignment(
                MediaCategoryAssignment(
                    media_asset_id=asset.id,
                    category_id=category.id,
                    quality_score=4,
                    fit_score=5,
                    role=AssignmentRole.TRAINING_CANDIDATE,
                    confidence=1.0,
                    notes=f"Synthetic Dark Bell v1 pack — {category.name}",
                    reviewed=True,
                )
            )

        # Mark PENDING so it appears in the training queue
        asset = asset.model_copy(update={
            "ingestion_status": IngestionStatus.PENDING,
            "ingested_fingerprint": None,
            "updated_at": now,
        })
        media_store.save(asset)

    return {
        "pack": PACK_NAME,
        "pack_dir": str(pack_dir),
        "imported_count": len(imported),
        "reused_count": len(reused),
        "total_clips": len(wav_files),
        "imported": imported,
        "reused": reused,
        "categories": {k: v.id for k, v in categories.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Synthetic Dark Bell v1 into Studio stores")
    parser.add_argument("--pack-dir", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = ingest_synthetic_pack(pack_dir=args.pack_dir)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Pack:      {report['pack']}")
        print(f"Pack dir:  {report['pack_dir']}")
        print(f"Total clips: {report['total_clips']}")
        print(f"Imported:  {report['imported_count']}")
        print(f"Reused:    {report['reused_count']}")
        print("Categories:")
        for label, cat_id in sorted(report["categories"].items()):
            print(f"  {label}: {cat_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
