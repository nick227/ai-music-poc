#!/usr/bin/env python3
"""Verify Phase 1 fixture audio -> Dataset Candidate -> frozen Dataset evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
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
from app.domain.enums import CategoryDimension, DatasetSliceStatus
from app.domain.seeds import category_seed_id
from app.services.category_service import CategoryService
from app.services.concept_service import ConceptService
from app.services.dataset_generator_service import DatasetGeneratorService
from app.services.ready_audio_service import ReadyAudioService
from app.services.slice_package_service import SlicePackageService
from app.services.slice_service import SliceService
from app.storage.assignment_store import AssignmentStore
from app.storage.category_store import CategoryStore
from app.storage.concept_store import ConceptStore
from app.storage.local_media_store import LocalMediaStore
from app.storage.slice_store import SliceStore
from scripts.ingest_fixture_audio import FIXTURE_MAP, ingest_fixtures


PRIMARY_CATEGORIES: dict[str, tuple[str, CategoryDimension]] = {
    "bell": ("Bell", CategoryDimension.INSTRUMENT),
    "chimes": ("Chimes", CategoryDimension.INSTRUMENT),
    "ocean": ("Ocean", CategoryDimension.GENRE),
}


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_hash_payload(manifest: dict) -> str:
    payload = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _services(settings):
    media_store = LocalMediaStore(settings.media_dir)
    assignment_store = AssignmentStore(settings.assignments_dir)
    category_service = CategoryService(CategoryStore(settings.categories_dir))
    concept_service = ConceptService(ConceptStore(settings.concepts_dir), category_service)
    slice_store = SliceStore(settings.slices_dir)
    package_service = SlicePackageService(slice_store, media_store, assignment_store, category_service, settings)
    slice_service = SliceService(
        slice_store,
        media_store,
        assignment_store,
        category_service,
        concept_service,
        package_service,
    )
    ready_audio_service = ReadyAudioService(media_store, assignment_store, concept_service, category_service)
    generator_service = DatasetGeneratorService(
        slice_service,
        category_service,
        assignment_store,
        media_store,
        ready_audio_service,
    )
    return {
        "media_store": media_store,
        "assignment_store": assignment_store,
        "category_service": category_service,
        "slice_store": slice_store,
        "slice_service": slice_service,
        "ready_audio_service": ready_audio_service,
        "generator_service": generator_service,
    }


def _assert_fixture_audio_exists(fixture_root: Path, clips_per_slug: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for slug in FIXTURE_MAP:
        files = sorted((fixture_root / slug).glob("*.wav"))
        counts[slug] = len(files)
        if len(files) < clips_per_slug:
            raise RuntimeError(f"Expected at least {clips_per_slug} fixture WAVs for {slug}, found {len(files)}")
    return counts


def _category_id(name: str, dimension: CategoryDimension) -> str:
    return category_seed_id(dimension, name.strip().lower().replace(" ", "-"))


def _candidate_for_category(candidates, category_id: str):
    for item in candidates:
        if (
            item.is_auto_generated
            and item.status == DatasetSliceStatus.DRAFT
            and item.filter.category_ids == [category_id]
        ):
            return item
    return None


def verify_fixture_dataset_flow(*, clips_per_slug: int = 12) -> dict:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()
    fixture_root = (settings.data_dir / "fixtures" / "audio").expanduser()
    if not fixture_root.is_absolute():
        fixture_root = (ROOT / fixture_root).resolve()

    ingest_report = ingest_fixtures(
        fixture_root=fixture_root,
        ensure_missing=True,
        clips_per_slug=clips_per_slug,
    )
    fixture_counts = _assert_fixture_audio_exists(fixture_root, clips_per_slug)
    services = _services(settings)

    ready_by_slug: dict[str, list[str]] = {}
    for asset in services["media_store"].list_recent(limit=100_000):
        fixture_slug = (asset.version_details or {}).get("fixture_slug")
        if fixture_slug not in FIXTURE_MAP:
            continue
        categories = services["assignment_store"].list_category_assignments_for_media(asset.id)
        concepts = services["assignment_store"].list_concept_assignments_for_media(asset.id)
        if services["ready_audio_service"].is_ready(asset, categories, concepts):
            ready_by_slug.setdefault(str(fixture_slug), []).append(asset.id)

    for slug in FIXTURE_MAP:
        if len(ready_by_slug.get(slug, [])) < clips_per_slug:
            raise RuntimeError(f"Expected at least {clips_per_slug} training-eligible {slug} fixtures")

    first_candidates = services["generator_service"].generate_recommended_slices()
    candidate_ids: dict[str, str] = {}
    for slug, (name, dimension) in PRIMARY_CATEGORIES.items():
        category_id = _category_id(name, dimension)
        candidate = _candidate_for_category(first_candidates, category_id)
        if candidate is None:
            raise RuntimeError(f"Missing Dataset Candidate for {name}")
        candidate_ids[slug] = candidate.id

    bell_candidate = services["slice_service"].get_required(candidate_ids["bell"])
    frozen = services["slice_service"].freeze(bell_candidate.id)
    manifest_path = settings.slices_dir / frozen.id / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"Frozen manifest was not written: {manifest_path}")
    manifest_before_text = manifest_path.read_text(encoding="utf-8")
    manifest_before_hash = _file_hash(manifest_path)
    manifest = json.loads(manifest_before_text)

    required_manifest_keys = {
        "media_ids",
        "tracks",
        "total_duration_seconds",
        "frozen_at",
        "manifest_hash",
    }
    missing_keys = sorted(required_manifest_keys - set(manifest))
    if missing_keys:
        raise RuntimeError(f"Frozen manifest missing keys: {missing_keys}")
    if manifest["manifest_hash"] != _manifest_hash_payload(manifest):
        raise RuntimeError("Frozen manifest_hash does not match manifest content")
    if not manifest["tracks"]:
        raise RuntimeError("Frozen manifest has no tracks")
    for track in manifest["tracks"]:
        if not track.get("file_path"):
            raise RuntimeError(f"Frozen track missing file_path: {track}")
        if not track.get("duration_seconds"):
            raise RuntimeError(f"Frozen track missing duration_seconds: {track}")
        if not track.get("categories"):
            raise RuntimeError(f"Frozen track missing categories: {track}")

    services["generator_service"].generate_recommended_slices()
    manifest_after_text = manifest_path.read_text(encoding="utf-8")
    manifest_after_hash = _file_hash(manifest_path)
    if manifest_after_text != manifest_before_text:
        raise RuntimeError("Frozen dataset manifest mutated after regenerating candidates")

    report = {
        "phase": "phase-1-fixture-dataset-flow",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "fixture_root": str(fixture_root),
        "fixture_counts": fixture_counts,
        "ingest": {
            "imported_count": ingest_report["imported_count"],
            "reused_count": ingest_report["reused_count"],
        },
        "ready_media_counts": {slug: len(ids) for slug, ids in sorted(ready_by_slug.items())},
        "candidate_ids": candidate_ids,
        "frozen_dataset": {
            "slice_id": frozen.id,
            "name": frozen.name,
            "version": frozen.version,
            "track_count": manifest["track_count"],
            "total_duration_seconds": manifest["total_duration_seconds"],
            "manifest_path": str(manifest_path),
            "manifest_file_hash_before": manifest_before_hash,
            "manifest_file_hash_after": manifest_after_hash,
            "manifest_hash": manifest["manifest_hash"],
            "immutable_after_regenerate": manifest_after_hash == manifest_before_hash,
        },
        "success": True,
    }
    report_dir = settings.data_dir / "experiments" / "fixture-dataset-flow"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Phase 1 fixture dataset flow")
    parser.add_argument("--clips-per-slug", type=int, default=12)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = verify_fixture_dataset_flow(clips_per_slug=args.clips_per_slug)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        frozen = report["frozen_dataset"]
        print("Fixture dataset flow: PASS")
        print(f"Fixture root: {report['fixture_root']}")
        print(f"Ready media counts: {report['ready_media_counts']}")
        print(f"Dataset candidates: {report['candidate_ids']}")
        print(f"Frozen dataset: {frozen['slice_id']} ({frozen['track_count']} tracks, {frozen['total_duration_seconds']}s)")
        print(f"Manifest: {frozen['manifest_path']}")
        print(f"Manifest hash: {frozen['manifest_hash']}")
        print(f"Report: {report['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
