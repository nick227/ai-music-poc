from __future__ import annotations

from app.domain.enums import CategoryDimension as D
from app.domain.seeds._core import CategorySeed

QUALITY_ISSUE_SEEDS: tuple[CategorySeed, ...] = (
    CategorySeed(D.QUALITY_ISSUE, "Weak Chorus", "weak-chorus"),
    CategorySeed(D.QUALITY_ISSUE, "Weak Verse", "weak-verse"),
    CategorySeed(D.QUALITY_ISSUE, "Weak Hook", "weak-hook"),
    CategorySeed(D.QUALITY_ISSUE, "Muddy Mix", "muddy-mix"),
    CategorySeed(D.QUALITY_ISSUE, "Harsh Highs", "harsh-highs"),
    CategorySeed(D.QUALITY_ISSUE, "Thin Low End", "thin-low-end"),
    CategorySeed(D.QUALITY_ISSUE, "Overcompressed", "overcompressed"),
    CategorySeed(D.QUALITY_ISSUE, "Clipping", "clipping"),
    CategorySeed(D.QUALITY_ISSUE, "Phase Issues", "phase-issues"),
    CategorySeed(D.QUALITY_ISSUE, "Timing Drift", "timing-drift"),
    CategorySeed(D.QUALITY_ISSUE, "Pitch Issues", "pitch-issues"),
    CategorySeed(D.QUALITY_ISSUE, "Off-Key Vocal", "off-key-vocal"),
    CategorySeed(D.QUALITY_ISSUE, "Robotic Vocal", "robotic-vocal"),
    CategorySeed(D.QUALITY_ISSUE, "Sibilant Vocal", "sibilant-vocal"),
    CategorySeed(D.QUALITY_ISSUE, "Breath Noise", "breath-noise"),
    CategorySeed(D.QUALITY_ISSUE, "Room Noise", "room-noise"),
    CategorySeed(D.QUALITY_ISSUE, "Click Track Bleed", "click-track-bleed"),
    CategorySeed(D.QUALITY_ISSUE, "Artifacting", "artifacting"),
    CategorySeed(D.QUALITY_ISSUE, "Loop Seam", "loop-seam"),
    CategorySeed(D.QUALITY_ISSUE, "Abrupt Ending", "abrupt-ending"),
    CategorySeed(D.QUALITY_ISSUE, "Repetitive", "repetitive"),
    CategorySeed(D.QUALITY_ISSUE, "Unbalanced Dynamics", "unbalanced-dynamics"),
    CategorySeed(D.QUALITY_ISSUE, "Genre Mismatch", "genre-mismatch"),
    CategorySeed(D.QUALITY_ISSUE, "Lyric-Groove Mismatch", "lyric-groove-mismatch"),
    CategorySeed(D.QUALITY_ISSUE, "Weak Arrangement", "weak-arrangement"),
    CategorySeed(D.QUALITY_ISSUE, "Overcrowded Mix", "overcrowded-mix"),
    CategorySeed(D.QUALITY_ISSUE, "Underdeveloped", "underdeveloped"),
    CategorySeed(D.QUALITY_ISSUE, "Generic", "generic"),
)
