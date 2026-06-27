from __future__ import annotations

from app.domain.enums import CategoryDimension as D
from app.domain.seeds._core import CategorySeed

ENERGY_SEEDS: tuple[CategorySeed, ...] = (
    CategorySeed(D.ENERGY, "Very Low", "very-low"),
    CategorySeed(D.ENERGY, "Low", "low"),
    CategorySeed(D.ENERGY, "Medium-Low", "medium-low"),
    CategorySeed(D.ENERGY, "Medium", "medium"),
    CategorySeed(D.ENERGY, "Medium-High", "medium-high"),
    CategorySeed(D.ENERGY, "High", "high"),
    CategorySeed(D.ENERGY, "Very High", "very-high"),
    CategorySeed(D.ENERGY, "Explosive", "explosive"),
)
