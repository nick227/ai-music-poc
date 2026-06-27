from __future__ import annotations

from typing import Optional

from app.core.errors import NotFoundError, ValidationAppError
from app.domain.enums import CategoryDimension, CategoryStatus
from app.domain.seeds import CATEGORY_SEEDS, category_from_seed, category_seed_id
from app.domain.taxonomy import Category
from app.domain.text_utils import slugify
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

    def create(self, name: str, dimension: CategoryDimension, slug: str | None = None, description: str | None = None) -> Category:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationAppError("Category name is required")

        clean_slug = slugify(slug or clean_name, fallback="category")
        category_id = category_seed_id(dimension, clean_slug)
        if self.store.exists(category_id):
            from uuid import uuid4

            category_id = f"{category_id}_{uuid4().hex[:8]}"

        category = Category(
            id=category_id,
            dimension=dimension,
            name=clean_name,
            slug=clean_slug,
            description=description.strip() if description else None,
            status=CategoryStatus.ACTIVE,
        )
        self.store.save(category)
        return category
