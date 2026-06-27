from __future__ import annotations

from pathlib import Path

from app.domain.taxonomy import Concept
from app.storage.json_entity_store import JsonEntityStore


class ConceptStore(JsonEntityStore[Concept]):
    def __init__(self, directory: Path) -> None:
        super().__init__(directory, Concept)

    def list_sorted(self) -> list[Concept]:
        records = self.list_all()
        records.sort(key=lambda item: item.name.lower())
        return records
