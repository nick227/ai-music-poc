from __future__ import annotations

from app.domain.enums import CategoryDimension as D
from app.domain.seeds._core import CategorySeed

RHYTHM_SEEDS: tuple[CategorySeed, ...] = (
    CategorySeed(D.RHYTHM, "Half-Time", "half-time"),
    CategorySeed(D.RHYTHM, "Double-Time", "double-time"),
    CategorySeed(D.RHYTHM, "Straight Eighths", "straight-eighths"),
    CategorySeed(D.RHYTHM, "Swung Eighths", "swung-eighths"),
    CategorySeed(D.RHYTHM, "Syncopated", "syncopated"),
    CategorySeed(D.RHYTHM, "Four-on-the-Floor", "four-on-the-floor"),
    CategorySeed(D.RHYTHM, "Backbeat", "backbeat"),
    CategorySeed(D.RHYTHM, "Shuffle", "shuffle"),
    CategorySeed(D.RHYTHM, "Bossa Nova Groove", "bossa-nova-groove"),
    CategorySeed(D.RHYTHM, "Reggae One-Drop", "reggae-one-drop"),
    CategorySeed(D.RHYTHM, "Trap Hi-Hats", "trap-hi-hats"),
    CategorySeed(D.RHYTHM, "Breakbeat", "breakbeat"),
    CategorySeed(D.RHYTHM, "Drum and Bass Break", "drum-and-bass-break"),
    CategorySeed(D.RHYTHM, "Waltz", "waltz"),
    CategorySeed(D.RHYTHM, "Compound Meter", "compound-meter"),
    CategorySeed(D.RHYTHM, "Odd Meter", "odd-meter"),
    CategorySeed(D.RHYTHM, "Polyrhythmic", "polyrhythmic"),
    CategorySeed(D.RHYTHM, "Rubato Feel", "rubato-feel"),
    CategorySeed(D.RHYTHM, "Driving Pulse", "driving-pulse"),
    CategorySeed(D.RHYTHM, "Laid-Back Groove", "laid-back-groove"),
    CategorySeed(D.RHYTHM, "Minimal Groove", "minimal-groove"),
    CategorySeed(D.RHYTHM, "Busy Groove", "busy-groove"),
    CategorySeed(D.RHYTHM, "March", "march"),
    CategorySeed(D.RHYTHM, "Ballad Tempo", "ballad-tempo"),
    CategorySeed(D.RHYTHM, "Up-Tempo", "up-tempo"),
    CategorySeed(D.RHYTHM, "Slow Burn", "slow-burn"),
    CategorySeed(D.RHYTHM, "Steady Pulse", "steady-pulse"),
    CategorySeed(D.RHYTHM, "Off-Beat Accent", "off-beat-accent"),
    CategorySeed(D.RHYTHM, "Triplet Feel", "triplet-feel"),
    CategorySeed(D.RHYTHM, "Latin Clave", "latin-clave"),
)
