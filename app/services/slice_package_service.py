from __future__ import annotations

import csv
import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.core.paths import safe_child_path
from app.domain.slices import DatasetSlice
from app.domain.taxonomy import MediaCategoryAssignment, MediaConceptAssignment
from app.services.category_service import CategoryService
from app.storage.assignment_store import AssignmentStore
from app.storage.local_media_store import LocalMediaStore
from app.storage.slice_store import SliceStore


class SlicePackageService:
    def __init__(
        self,
        slice_store: SliceStore,
        media_store: LocalMediaStore,
        assignment_store: AssignmentStore,
        category_service: CategoryService,
        settings: Settings,
    ) -> None:
        self.slice_store = slice_store
        self.media_store = media_store
        self.assignment_store = assignment_store
        self.category_service = category_service
        self.settings = settings

    def build_manifest(self, slice_record: DatasetSlice) -> dict:
        manifest = self.slice_store.read_manifest(slice_record.id)
        if manifest is not None:
            return manifest
        return {
            "format_version": 1,
            "package_type": "ace-training",
            "slice_id": slice_record.id,
            "name": slice_record.name,
            "version": slice_record.version,
            "concept_id": slice_record.filter.concept_id,
            "track_count": len(slice_record.frozen_media_ids or slice_record.media_ids),
            "filters": slice_record.filter.model_dump(mode="json"),
            "media_ids": slice_record.frozen_media_ids or slice_record.media_ids,
            "frozen_at": slice_record.frozen_at.isoformat() if slice_record.frozen_at else None,
        }

    def create_package(self, slice_record: DatasetSlice) -> Path:
        media_ids = slice_record.frozen_media_ids or slice_record.media_ids
        if not media_ids:
            raise ValueError("Slice has no media to package")

        tmp = Path(tempfile.gettempdir()) / f"{slice_record.id}-package.zip"
        manifest = self.build_manifest(slice_record)
        rights_rows: list[dict] = []
        caption_rows: list[dict] = []

        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("training-package/manifest.json", json.dumps(manifest, indent=2))
            for media_id in media_ids:
                asset = self.media_store.get(media_id)
                if asset is None or not asset.file_path:
                    continue
                source = safe_child_path(self.settings.data_dir, asset.file_path)
                frozen = self.slice_store.audio_dir(slice_record.id) / f"{media_id}.wav"
                audio_source = frozen if frozen.exists() else source
                archive_audio = f"training-package/tracks/{media_id}/audio.wav"
                zf.write(audio_source, archive_audio)

                labels = self._track_labels(media_id)
                caption = self._track_caption(labels)
                lyrics = self._track_lyrics(asset)
                annotation = self._track_annotation(asset, labels, caption, lyrics, archive_audio)
                zf.writestr(
                    f"training-package/tracks/{media_id}/labels.json",
                    json.dumps(labels, indent=2),
                )
                zf.writestr(f"training-package/tracks/{media_id}/caption.txt", caption)
                zf.writestr(
                    f"training-package/tracks/{media_id}/annotation.json",
                    json.dumps(annotation, indent=2),
                )
                if lyrics:
                    zf.writestr(f"training-package/tracks/{media_id}/lyrics.txt", lyrics)
                rights_rows.append({"media_id": media_id, "rights_status": asset.rights_status.value})
                caption_rows.append(
                    {
                        "path": archive_audio,
                        "caption": caption,
                        "lyrics_path": f"training-package/tracks/{media_id}/lyrics.txt" if lyrics else "",
                        "annotation_path": f"training-package/tracks/{media_id}/annotation.json",
                    }
                )

            zf.writestr("training-package/rights.json", json.dumps(rights_rows, indent=2))
            zf.writestr("training-package/captions.csv", self._captions_csv(caption_rows))

        return tmp

    def _track_labels(self, media_id: str) -> dict:
        categories = self.assignment_store.list_category_assignments_for_media(media_id)
        concepts = self.assignment_store.list_concept_assignments_for_media(media_id)
        category_labels = []
        for assignment in categories:
            try:
                category = self.category_service.get_required(assignment.category_id)
                name = category.name
                dimension = category.dimension.value
            except NotFoundError:
                name = assignment.category_id
                dimension = None
            category_labels.append(
                {
                    "category_id": assignment.category_id,
                    "name": name,
                    "dimension": dimension,
                    "role": assignment.role.value,
                    "quality_score": assignment.quality_score,
                    "fit_score": assignment.fit_score,
                    "notes": assignment.notes,
                }
            )
        return {
            "media_id": media_id,
            "concept_ids": [item.concept_id for item in concepts],
            "concepts": [self._concept_assignment_label(item) for item in concepts],
            "categories": category_labels,
            "tags": self._taxonomy_tags(category_labels, concepts),
        }

    def _track_caption(self, labels: dict) -> str:
        names = labels.get("tags", [])
        return " | ".join(names) if names else labels["media_id"]

    def _captions_csv(self, rows: list[dict]) -> str:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=["path", "caption", "lyrics_path", "annotation_path"])
        writer.writeheader()
        writer.writerows(rows)
        return buffer.getvalue()

    def _concept_assignment_label(self, assignment: MediaConceptAssignment) -> dict:
        return {
            "concept_id": assignment.concept_id,
            "role": assignment.role.value,
            "quality_score": assignment.quality_score,
            "fit_score": assignment.fit_score,
            "notes": assignment.notes,
        }

    def _taxonomy_tags(
        self,
        category_labels: list[dict],
        concepts: list[MediaConceptAssignment],
    ) -> list[str]:
        tags: list[str] = []
        for concept in concepts:
            tags.append(concept.concept_id)
        preferred_dimensions = {
            "GENRE",
            "MOOD",
            "VOCALS",
            "INSTRUMENT",
            "PRODUCTION",
            "MIX",
            "RHYTHM",
            "ARRANGEMENT",
            "ENERGY",
            "TECHNIQUE",
        }
        for item in category_labels:
            name = item.get("name")
            if name and item.get("dimension") in preferred_dimensions:
                tags.append(name)
        deduped: list[str] = []
        for tag in tags:
            clean = str(tag).strip()
            if clean and clean not in deduped:
                deduped.append(clean)
        return deduped

    def _track_lyrics(self, asset) -> str:
        version_details = asset.version_details or {}
        lyrics = version_details.get("lyrics")
        return lyrics.strip() if isinstance(lyrics, str) else ""

    def _track_annotation(self, asset, labels: dict, caption: str, lyrics: str, audio_path: str) -> dict:
        version_details = asset.version_details or {}
        settings = version_details.get("settings") if isinstance(version_details.get("settings"), dict) else {}
        return {
            "format_version": 1,
            "media_id": asset.id,
            "title": asset.title,
            "audio_path": audio_path,
            "lyrics_path": "lyrics.txt" if lyrics else None,
            "caption": caption,
            "tags": labels.get("tags", []),
            "taxonomy": labels,
            "signals": {
                "review_status": asset.review_status.value,
                "rights_status": asset.rights_status.value,
                "review_decision": asset.review_decision.value if asset.review_decision else None,
                "review_score": asset.review_score,
            },
            "music": {
                "bpm": settings.get("bpm") or version_details.get("bpm"),
                "key": settings.get("key") or version_details.get("key"),
                "time_signature": settings.get("timeSignature") or version_details.get("time_signature"),
                "duration_seconds": asset.duration_seconds,
                "sample_rate": asset.sample_rate,
                "channels": asset.channels,
            },
        }

    def copy_audio_for_freeze(self, slice_id: str, media_ids: list[str]) -> None:
        audio_dir = self.slice_store.audio_dir(slice_id)
        for media_id in media_ids:
            asset = self.media_store.get(media_id)
            if asset is None or not asset.file_path:
                continue
            source = safe_child_path(self.settings.data_dir, asset.file_path)
            dest = audio_dir / f"{media_id}.wav"
            shutil.copy2(source, dest)
