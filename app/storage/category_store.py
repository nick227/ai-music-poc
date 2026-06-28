from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.domain.enums import CategoryDimension, CategoryStatus
from app.domain.taxonomy import Category
from app.storage.json_entity_store import JsonEntityStore


class CategoryStore(JsonEntityStore[Category]):
    def __init__(self, directory: Path) -> None:
        super().__init__(directory, Category)

    def list_filtered(self, dimension: Optional[CategoryDimension] = None, include_archived: bool = False) -> list[Category]:
        records = self.list_all()
        if not include_archived:
            records = [item for item in records if item.status != CategoryStatus.ARCHIVED]
        if dimension is not None:
            records = [item for item in records if item.dimension == dimension]
        records.sort(key=lambda item: (item.dimension.value, item.name.lower()))
        return records
