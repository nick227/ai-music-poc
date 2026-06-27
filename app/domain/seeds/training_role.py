from __future__ import annotations

from app.domain.enums import CategoryDimension as D
from app.domain.seeds._core import CategorySeed

TRAINING_ROLE_SEEDS: tuple[CategorySeed, ...] = (
    CategorySeed(D.TRAINING_ROLE, "Gold Reference", "gold-reference"),
    CategorySeed(D.TRAINING_ROLE, "Style Reference", "style-reference"),
    CategorySeed(D.TRAINING_ROLE, "Vocal Reference", "vocal-reference"),
    CategorySeed(D.TRAINING_ROLE, "Mix Reference", "mix-reference"),
    CategorySeed(D.TRAINING_ROLE, "Production Reference", "production-reference"),
    CategorySeed(D.TRAINING_ROLE, "Training Candidate", "training-candidate"),
    CategorySeed(D.TRAINING_ROLE, "Generated Test", "generated-test"),
    CategorySeed(D.TRAINING_ROLE, "Negative Example", "negative-example"),
    CategorySeed(D.TRAINING_ROLE, "Edge Case", "edge-case"),
    CategorySeed(D.TRAINING_ROLE, "Benchmark", "benchmark"),
    CategorySeed(D.TRAINING_ROLE, "A/B Variant", "ab-variant"),
    CategorySeed(D.TRAINING_ROLE, "Curated Keeper", "curated-keeper"),
)
