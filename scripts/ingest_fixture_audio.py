#!/usr/bin/env python3
"""Ingest deterministic fixture audio into the Studio media/category stores."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
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

FIXTURE_MAP: dict[str, list[tuple[str, CategoryDimension]]] = {
    "bell": [
        ("Bell", CategoryDimension.INSTRUMENT),
        ("Metallic", CategoryDimension.PRODUCTION),
        ("One Shot", CategoryDimension.ARRANGEMENT),
    ],
    "chimes": [
        ("Chimes", CategoryDimension.INSTRUMENT),
        ("Metallic", CategoryDimension.PRODUCTION),
        ("Ambient", CategoryDimension.GENRE),
    ],
    "ocean": [
        ("Ocean", CategoryDimension.GENRE),
        ("Natural", CategoryDimension.PRODUCTION),
        ("Ambient", CategoryDimension.GENRE),
        ("Loopable", CategoryDimension.ARRANGEMENT),
    ],
}


def _slug(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_audio(path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    result = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    fmt = data.get("format", {})
    stream = next((item for item in data.get("streams", []) if item.get("codec_type") == "audio"), {})
    return {
        "duration_seconds": round(float(fmt.get("duration") or stream.get("duration") or 0), 3),
        "sample_rate": int(stream.get("sample_rate") or 0),
        "channels": int(stream.get("channels") or 0),
    }


def _write_wav(path: Path, *, slug: str, index: int, duration_seconds: float = 5.0, sample_rate: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = int(duration_seconds * sample_rate)
    frames = bytearray()
    for n in range(frame_count):
        t = n / sample_rate
        if slug == "bell":
            env = math.exp(-2.8 * (t % duration_seconds))
            sample = env * (math.sin(2 * math.pi * (660 + index * 9) * t) + 0.45 * math.sin(2 * math.pi * (1320 + index * 11) * t))
        elif slug == "chimes":
            env = 0.35 + 0.65 * math.exp(-1.1 * (t % 1.7))
            sample = env * (
                0.45 * math.sin(2 * math.pi * (880 + index * 7) * t)
                + 0.35 * math.sin(2 * math.pi * (1175 + index * 5) * t)
                + 0.25 * math.sin(2 * math.pi * (1568 + index * 3) * t)
            )
        else:
            slow = math.sin(2 * math.pi * (0.08 + index * 0.002) * t)
            texture = math.sin(2 * math.pi * (95 + index) * t) + 0.5 * math.sin(2 * math.pi * (137 + index * 2) * t)
            sample = 0.45 * slow + 0.25 * texture + 0.12 * math.sin(2 * math.pi * (23 + index) * t)
        value = max(-0.95, min(0.95, sample * 0.45))
        frames.extend(struct.pack("<h", int(value * 32767)))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(frames))


def ensure_fixture_audio(fixture_root: Path, clips_per_slug: int, duration_seconds: float) -> None:
    for slug in FIXTURE_MAP:
        for index in range(1, clips_per_slug + 1):
            path = fixture_root / slug / f"{slug}-{index:02d}.wav"
            if not path.exists():
                _write_wav(path, slug=slug, index=index, duration_seconds=duration_seconds)


def _resolve_category(service: CategoryService, name: str, dimension: CategoryDimension):
    slug = _slug(name)
    expected_id = category_seed_id(dimension, slug)
    existing = service.store.get(expected_id)
    if existing is not None:
        return existing
    for category in service.list(dimension=dimension, include_archived=False):
        if category.slug == slug:
            return category
    return service.create(name=name, dimension=dimension, slug=slug, description="Fixture evidence category")


def _find_existing_by_hash(media_store: LocalMediaStore, file_hash: str) -> MediaAsset | None:
    for asset in media_store.list_recent(limit=100_000):
        details = asset.version_details or {}
        if details.get("fixture_sha256") == file_hash:
            return asset
    return None


def ingest_fixtures(*, fixture_root: Path | None = None, ensure_missing: bool = False, clips_per_slug: int = 12) -> dict:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()
    fixture_root = fixture_root or (settings.data_dir / "fixtures" / "audio")
    fixture_root = fixture_root.expanduser()
    if not fixture_root.is_absolute():
        fixture_root = (ROOT / fixture_root).resolve()

    if ensure_missing:
        ensure_fixture_audio(fixture_root, clips_per_slug=clips_per_slug, duration_seconds=5.0)

    category_service = CategoryService(CategoryStore(settings.categories_dir))
    media_store = LocalMediaStore(settings.media_dir)
    assignment_store = AssignmentStore(settings.assignments_dir)

    imported: list[dict] = []
    reused: list[dict] = []
    categories_created_or_resolved: dict[str, str] = {}

    for slug, category_specs in FIXTURE_MAP.items():
        files = sorted((fixture_root / slug).glob("*.wav"))
        for path in files:
            file_hash = _sha256(path)
            probe = _probe_audio(path)
            asset = _find_existing_by_hash(media_store, file_hash)
            relative_path = path.relative_to(settings.data_dir.resolve()) if path.is_relative_to(settings.data_dir.resolve()) else path
            now = datetime.now(timezone.utc)
            if asset is None:
                asset = MediaAsset(
                    title=f"{slug.title()} Fixture {path.stem.rsplit('-', 1)[-1]}",
                    kind=MediaKind.UPLOAD,
                    source=MediaSource.USER_IMPORT,
                    file_path=relative_path.as_posix(),
                    duration_seconds=probe["duration_seconds"],
                    sample_rate=probe["sample_rate"],
                    channels=probe["channels"],
                    review_status=ReviewStatus.REVIEWED,
                    rights_status=RightsStatus.CONFIRMED,
                    version_details={
                        "fixture_slug": slug,
                        "fixture_path": str(path),
                        "fixture_sha256": file_hash,
                    },
                    updated_at=now,
                )
                media_store.save(asset)
                imported.append({"media_id": asset.id, "slug": slug, "path": str(path), "sha256": file_hash})
            else:
                asset = asset.model_copy(
                    update={
                        "file_path": relative_path.as_posix(),
                        "duration_seconds": probe["duration_seconds"],
                        "sample_rate": probe["sample_rate"],
                        "channels": probe["channels"],
                        "review_status": ReviewStatus.REVIEWED,
                        "rights_status": RightsStatus.CONFIRMED,
                        "updated_at": now,
                    }
                )
                media_store.save(asset)
                reused.append({"media_id": asset.id, "slug": slug, "path": str(path), "sha256": file_hash})

            for name, dimension in category_specs:
                category = _resolve_category(category_service, name, dimension)
                categories_created_or_resolved[f"{dimension.value}:{name}"] = category.id
                assignment_store.upsert_category_assignment(
                    MediaCategoryAssignment(
                        media_asset_id=asset.id,
                        category_id=category.id,
                        quality_score=4,
                        fit_score=4,
                        role=AssignmentRole.TRAINING_CANDIDATE,
                        confidence=1.0,
                        notes=f"Deterministic fixture tag: {slug}",
                        reviewed=True,
                    )
                )
            asset = asset.model_copy(
                update={
                    "ingestion_status": IngestionStatus.PENDING,
                    "ingested_fingerprint": None,
                    "updated_at": now,
                }
            )
            media_store.save(asset)

    report = {
        "fixture_root": str(fixture_root),
        "imported_count": len(imported),
        "reused_count": len(reused),
        "imported": imported,
        "reused": reused,
        "categories": categories_created_or_resolved,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest categorized fixture audio for Phase 1 dataset evidence")
    parser.add_argument("--fixture-root", type=Path, default=None)
    parser.add_argument("--ensure-fixtures", action="store_true", help="Generate deterministic 5s WAV fixtures when missing")
    parser.add_argument("--clips-per-slug", type=int, default=12)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = ingest_fixtures(
        fixture_root=args.fixture_root,
        ensure_missing=args.ensure_fixtures,
        clips_per_slug=args.clips_per_slug,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Fixture root: {report['fixture_root']}")
        print(f"Imported: {report['imported_count']}")
        print(f"Reused:   {report['reused_count']}")
        print("Categories:")
        for label, category_id in sorted(report["categories"].items()):
            print(f"  - {label}: {category_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
