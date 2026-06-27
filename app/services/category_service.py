from __future__ import annotations

import re
from typing import Optional

from app.core.errors import NotFoundError
from app.domain.enums import CategoryDimension
from app.domain.seeds import CATEGORY_SEEDS, category_from_seed
from app.domain.taxonomy import Category
from app.storage.category_store import CategoryStore


class CategoryService:
    def __init__(self, store: CategoryStore) -> None:
        self.store = store

    def seed_if_empty(self) -> list[Category]:
        for seed in CATEGORY_SEEDS:
            category = category_from_seed(seed)
            if not self.store.exists(category.id):
                self.store.save(category)
        return self.list()

    def list(self, dimension: Optional[CategoryDimension] = None) -> list[Category]:
        return self.store.list_filtered(dimension)

    def get_required(self, category_id: str) -> Category:
        category = self.store.get(category_id)
        if category is None:
            raise NotFoundError(f"Category not found: {category_id}")
        return category
