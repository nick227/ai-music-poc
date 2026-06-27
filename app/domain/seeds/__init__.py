from __future__ import annotations

from app.domain.seeds._core import CategorySeed, category_from_seed, category_seed_id
from app.domain.seeds.arrangement import ARRANGEMENT_SEEDS
from app.domain.seeds.energy import ENERGY_SEEDS
from app.domain.seeds.genre import GENRE_SEEDS
from app.domain.seeds.instrument import INSTRUMENT_SEEDS
from app.domain.seeds.mix import MIX_SEEDS
from app.domain.seeds.mood import MOOD_SEEDS
from app.domain.seeds.production import PRODUCTION_SEEDS
from app.domain.seeds.quality_issue import QUALITY_ISSUE_SEEDS
from app.domain.seeds.rhythm import RHYTHM_SEEDS
from app.domain.seeds.technique import TECHNIQUE_SEEDS
from app.domain.seeds.training_role import TRAINING_ROLE_SEEDS
from app.domain.seeds.vocals import VOCAL_SEEDS

CATEGORY_SEEDS: tuple[CategorySeed, ...] = (
    *GENRE_SEEDS,
    *MOOD_SEEDS,
    *INSTRUMENT_SEEDS,
    *TECHNIQUE_SEEDS,
    *PRODUCTION_SEEDS,
    *MIX_SEEDS,
    *RHYTHM_SEEDS,
    *VOCAL_SEEDS,
    *ARRANGEMENT_SEEDS,
    *ENERGY_SEEDS,
    *QUALITY_ISSUE_SEEDS,
    *TRAINING_ROLE_SEEDS,
)

__all__ = [
    "CATEGORY_SEEDS",
    "CategorySeed",
    "category_from_seed",
    "category_seed_id",
]
