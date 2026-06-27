from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import CategoryDimension
from app.domain.taxonomy import Category, CategoryStatus


@dataclass(frozen=True)
class CategorySeed:
    dimension: CategoryDimension
    name: str
    slug: str
    description: str | None = None


def category_seed_id(dimension: CategoryDimension, slug: str) -> str:
    return f"cat_{dimension.value.lower()}_{slug}"


def category_from_seed(seed: CategorySeed) -> Category:
    return Category(
        id=category_seed_id(seed.dimension, seed.slug),
        dimension=seed.dimension,
        name=seed.name,
        slug=seed.slug,
        description=seed.description,
        status=CategoryStatus.ACTIVE,
    )


CATEGORY_SEEDS: tuple[CategorySeed, ...] = (
    CategorySeed(CategoryDimension.GENRE, "Cinematic", "cinematic"),
    CategorySeed(CategoryDimension.MOOD, "Haunting", "haunting"),
    CategorySeed(CategoryDimension.INSTRUMENT, "Piano", "piano"),
    CategorySeed(CategoryDimension.TECHNIQUE, "Ghost Notes", "ghost-notes"),
    CategorySeed(CategoryDimension.PRODUCTION, "Dark Reverb", "dark-reverb"),
    CategorySeed(CategoryDimension.MIX, "Vocal Forward", "vocal-forward"),
    CategorySeed(CategoryDimension.RHYTHM, "Half-Time", "half-time"),
    CategorySeed(CategoryDimension.VOCALS, "Intimate Male", "intimate-male"),
    CategorySeed(CategoryDimension.ARRANGEMENT, "Sparse", "sparse"),
    CategorySeed(CategoryDimension.ENERGY, "Low", "low"),
    CategorySeed(CategoryDimension.ENERGY, "High", "high"),
    CategorySeed(CategoryDimension.QUALITY_ISSUE, "Weak Chorus", "weak-chorus"),
    CategorySeed(CategoryDimension.TRAINING_ROLE, "Gold Reference", "gold-reference"),
)
