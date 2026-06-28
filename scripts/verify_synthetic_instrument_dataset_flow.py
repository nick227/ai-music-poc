#!/usr/bin/env python3
"""Verify Synthetic Dark Bell v1 pack → Dataset Candidate → frozen Dataset flow.

Steps:
  1. Generate pack if WAV files are missing.
  2. Ingest clips as MediaAssets with categories.
  3. Generate Dataset Candidates via DatasetGeneratorService.
  4. Find the Bell INSTRUMENT candidate and freeze it.
  5. Verify manifest structure, hash integrity, and immutability.
"""

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

from scripts.generate_synthetic_instrument_pack import (
    PACK_NAME,
    DEFAULT_COUNT,
    generate_pack,
)
from scripts.ingest_synthetic_instrument_pack import (
    PACK_CATEGORY_SPECS,
    ingest_synthetic_pack,
)

# The primary category we use to locate the Dataset Candidate
PRIMARY_CATEGORY = ("Bell", CategoryDimension.INSTRUMENT)
# Minimum clips expected to be ready before proceeding
MIN_READY = 10


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_hash_payload(manifest: dict) -> str:
    payload = {k: v for k, v in manifest.items() if k != "manifest_hash"}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _build_services(settings):
    media_store = LocalMediaStore(settings.media_dir)
    assignment_store = AssignmentStore(settings.assignments_dir)
    category_service = CategoryService(CategoryStore(settings.categories_dir))
    concept_service = ConceptService(ConceptStore(settings.concepts_dir), category_service)
    slice_store = SliceStore(settings.slices_dir)
    package_service = SlicePackageService(slice_store, media_store, assignment_store,
                                          category_service, settings)
    slice_service = SliceService(slice_store, media_store, assignment_store,
                                 category_service, concept_service, package_service)
    ready_audio_service = ReadyAudioService(media_store, assignment_store, concept_service,
                                            category_service)
    generator_service = DatasetGeneratorService(slice_service, category_service,
                                                assignment_store, media_store,
                                                ready_audio_service)
    return {
        "media_store": media_store,
        "assignment_store": assignment_store,
        "category_service": category_service,
        "slice_service": slice_service,
        "ready_audio_service": ready_audio_service,
        "generator_service": generator_service,
    }


def _count_ready(services: dict, pack_name: str) -> int:
    count = 0
    for asset in services["media_store"].list_recent(limit=100_000):
        vd = asset.version_details or {}
        if vd.get("pack") != pack_name:
            continue
        categories = services["assignment_store"].list_category_assignments_for_media(asset.id)
        concepts = services["assignment_store"].list_concept_assignments_for_media(asset.id)
        if services["ready_audio_service"].is_ready(asset, categories, concepts):
            count += 1
    return count


def _find_bell_candidate(candidates, bell_cat_id: str):
    for item in candidates:
        if (
            item.is_auto_generated
            and item.status == DatasetSliceStatus.DRAFT
            and bell_cat_id in item.filter.category_ids
        ):
            return item
    return None


def verify_synthetic_instrument_dataset_flow(
    *,
    pack_dir: Path | None = None,
    clip_count: int = DEFAULT_COUNT,
    min_dur: float = 8.0,
    max_dur: float = 15.0,
) -> dict:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()

    pack_dir = pack_dir or (settings.data_dir / "synthetic_audio" / PACK_NAME)
    pack_dir = pack_dir.expanduser()
    if not pack_dir.is_absolute():
        pack_dir = (ROOT / pack_dir).resolve()

    # ── Step 1: generate pack if missing ──────────────────────────────────────
    existing_wavs = list(pack_dir.glob("*.wav"))
    if len(existing_wavs) < clip_count:
        print(f"Generating {clip_count} clips → {pack_dir}")
        generate_pack(pack_dir, count=clip_count, min_dur=min_dur, max_dur=max_dur, verbose=True)
    else:
        print(f"Pack already present ({len(existing_wavs)} clips) — skipping generation")

    wav_count = len(list(pack_dir.glob("*.wav")))
    if wav_count < clip_count:
        raise RuntimeError(f"Expected {clip_count} WAV clips, found {wav_count}")

    # ── Step 2: ingest clips ───────────────────────────────────────────────────
    print("Ingesting clips…")
    ingest_report = ingest_synthetic_pack(pack_dir=pack_dir)
    print(f"  imported={ingest_report['imported_count']}  reused={ingest_report['reused_count']}")

    services = _build_services(settings)

    # ── Step 3: verify ready media ─────────────────────────────────────────────
    ready_count = _count_ready(services, PACK_NAME)
    print(f"Ready clips: {ready_count}")
    if ready_count < MIN_READY:
        raise RuntimeError(f"Expected at least {MIN_READY} ready clips, got {ready_count}")

    # ── Step 4: generate Dataset Candidates ───────────────────────────────────
    print("Generating Dataset Candidates…")
    candidates = services["generator_service"].generate_recommended_slices()
    print(f"  Candidates found: {len(candidates)}")

    bell_cat_id = category_seed_id(PRIMARY_CATEGORY[1], "bell")
    bell_candidate = _find_bell_candidate(candidates, bell_cat_id)
    if bell_candidate is None:
        raise RuntimeError(
            f"No DRAFT Dataset Candidate found containing Bell ({bell_cat_id}). "
            f"Candidate category IDs: {[c.filter.category_ids for c in candidates[:5]]}"
        )

    print(f"  Bell candidate: {bell_candidate.id}  ({len(bell_candidate.media_ids)} tracks)")

    # ── Step 5: freeze ────────────────────────────────────────────────────────
    print("Freezing Bell dataset…")
    frozen = services["slice_service"].freeze(bell_candidate.id)
    manifest_path = settings.slices_dir / frozen.id / "manifest.json"

    if not manifest_path.is_file():
        raise RuntimeError(f"Frozen manifest not written: {manifest_path}")

    manifest_text_before = manifest_path.read_text(encoding="utf-8")
    hash_before = _file_hash(manifest_path)
    manifest = json.loads(manifest_text_before)

    # ── Step 6: verify manifest structure ─────────────────────────────────────
    required_keys = {"media_ids", "tracks", "total_duration_seconds", "frozen_at", "manifest_hash"}
    missing = sorted(required_keys - set(manifest))
    if missing:
        raise RuntimeError(f"Manifest missing keys: {missing}")

    if manifest["manifest_hash"] != _manifest_hash_payload(manifest):
        raise RuntimeError("manifest_hash does not match computed hash of manifest content")

    if not manifest["tracks"]:
        raise RuntimeError("Frozen manifest has no tracks")

    for track in manifest["tracks"]:
        for field in ("file_path", "duration_seconds", "categories"):
            if not track.get(field):
                raise RuntimeError(f"Frozen track missing {field}: {track}")

    # ── Step 7: immutability check ────────────────────────────────────────────
    services["generator_service"].generate_recommended_slices()
    hash_after = _file_hash(manifest_path)
    manifest_text_after = manifest_path.read_text(encoding="utf-8")

    if manifest_text_after != manifest_text_before:
        raise RuntimeError("Frozen dataset manifest mutated after regenerating candidates")

    # ── Report ─────────────────────────────────────────────────────────────────
    report = {
        "phase": "synthetic-dark-bell-v1-dataset-flow",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "pack": PACK_NAME,
        "pack_dir": str(pack_dir),
        "wav_count": wav_count,
        "ingest": {
            "imported_count": ingest_report["imported_count"],
            "reused_count": ingest_report["reused_count"],
        },
        "ready_count": ready_count,
        "candidate_count": len(candidates),
        "bell_candidate_id": bell_candidate.id,
        "frozen_dataset": {
            "slice_id": frozen.id,
            "name": frozen.name,
            "version": frozen.version,
            "track_count": manifest.get("track_count", len(manifest["tracks"])),
            "total_duration_seconds": manifest["total_duration_seconds"],
            "manifest_path": str(manifest_path),
            "manifest_hash": manifest["manifest_hash"],
            "hash_before": hash_before,
            "hash_after": hash_after,
            "immutable_after_regenerate": hash_after == hash_before,
        },
        "success": True,
    }

    report_dir = settings.data_dir / "experiments" / "synthetic-dark-bell-v1-dataset-flow"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Synthetic Dark Bell v1 pack → frozen Dataset flow"
    )
    parser.add_argument("--pack-dir", type=Path, default=None)
    parser.add_argument("--clip-count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--min-dur", type=float, default=8.0)
    parser.add_argument("--max-dur", type=float, default=15.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = verify_synthetic_instrument_dataset_flow(
        pack_dir=args.pack_dir,
        clip_count=args.clip_count,
        min_dur=args.min_dur,
        max_dur=args.max_dur,
    )

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        fd = report["frozen_dataset"]
        print("\nSynthetic Dark Bell v1 dataset flow: PASS")
        print(f"  Pack dir:        {report['pack_dir']}")
        print(f"  WAV clips:       {report['wav_count']}")
        print(f"  Ready clips:     {report['ready_count']}")
        print(f"  Candidates:      {report['candidate_count']}")
        print(f"  Bell candidate:  {report['bell_candidate_id']}")
        print(f"  Frozen dataset:  {fd['slice_id']}  ({fd['track_count']} tracks, {fd['total_duration_seconds']}s)")
        print(f"  Manifest hash:   {fd['manifest_hash']}")
        print(f"  Immutable:       {fd['immutable_after_regenerate']}")
        print(f"  Report:          {report['report_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
