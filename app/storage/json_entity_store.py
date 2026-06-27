from __future__ import annotations

from pathlib import Path
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class JsonEntityStore(Generic[T]):
    def __init__(self, directory: Path, model_class: type[T]) -> None:
        self.directory = directory
        self.model_class = model_class
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path_for(self, entity_id: str) -> Path:
        return self.directory / f"{entity_id}.json"

    def save(self, entity: T) -> None:
        entity_id = getattr(entity, "id")
        path = self._path_for(entity_id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(entity.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)

    def get(self, entity_id: str) -> Optional[T]:
        path = self._path_for(entity_id)
        if not path.exists():
            return None
        return self.model_class.model_validate_json(path.read_text(encoding="utf-8"))

    def exists(self, entity_id: str) -> bool:
        return self._path_for(entity_id).exists()

    def list_all(self) -> list[T]:
        records: list[T] = []
        for path in self.directory.glob("*.json"):
            try:
                records.append(self.model_class.model_validate_json(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return records
