from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.domain.slices import DatasetSlice


class SliceStore:
    def __init__(self, slices_dir: Path) -> None:
        self.slices_dir = slices_dir
        self.slices_dir.mkdir(parents=True, exist_ok=True)

    def slice_dir(self, slice_id: str) -> Path:
        return self.slices_dir / slice_id

    def save(self, slice_record: DatasetSlice) -> None:
        directory = self.slice_dir(slice_record.id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "slice.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(slice_record.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)

    def get(self, slice_id: str) -> Optional[DatasetSlice]:
        path = self.slice_dir(slice_id) / "slice.json"
        if not path.exists():
            return None
        return DatasetSlice.model_validate_json(path.read_text(encoding="utf-8"))

    def list_all(self) -> list[DatasetSlice]:
        records: list[DatasetSlice] = []
        if not self.slices_dir.exists():
            return records
        for directory in self.slices_dir.iterdir():
            if not directory.is_dir():
                continue
            path = directory / "slice.json"
            if not path.exists():
                continue
            try:
                records.append(DatasetSlice.model_validate_json(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        records.sort(key=lambda item: item.updated_at, reverse=True)
        return records

    def write_manifest(self, slice_id: str, manifest: dict) -> Path:
        directory = self.slice_dir(slice_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return path

    def read_manifest(self, slice_id: str) -> Optional[dict]:
        path = self.slice_dir(slice_id) / "manifest.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def audio_dir(self, slice_id: str) -> Path:
        directory = self.slice_dir(slice_id) / "audio"
        directory.mkdir(parents=True, exist_ok=True)
        return directory
