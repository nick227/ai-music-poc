from __future__ import annotations

import json
from pathlib import Path

from app.domain.style_versions import StyleVersion


class StyleVersionStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, version_id: str) -> Path:
        return self.root_dir / version_id / "version.json"

    def save(self, record: StyleVersion) -> StyleVersion:
        path = self._path(record.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return record

    def get(self, version_id: str) -> StyleVersion | None:
        path = self._path(version_id)
        if not path.exists():
            return None
        return StyleVersion.model_validate_json(path.read_text(encoding="utf-8"))

    def list_all(self) -> list[StyleVersion]:
        records: list[StyleVersion] = []
        if not self.root_dir.exists():
            return records
        for child in self.root_dir.iterdir():
            if not child.is_dir():
                continue
            record = self.get(child.name)
            if record is not None:
                records.append(record)
        records.sort(key=lambda item: item.created_at, reverse=True)
        return records
