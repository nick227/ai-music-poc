from __future__ import annotations

from app.domain.enums import CategoryDimension as D
from app.domain.seeds._core import CategorySeed

MIX_SEEDS: tuple[CategorySeed, ...] = (
    CategorySeed(D.MIX, "Vocal Forward", "vocal-forward"),
    CategorySeed(D.MIX, "Instrument Forward", "instrument-forward"),
    CategorySeed(D.MIX, "Balanced Mix", "balanced-mix"),
    CategorySeed(D.MIX, "Wide Stereo", "wide-stereo"),
    CategorySeed(D.MIX, "Narrow Stereo", "narrow-stereo"),
    CategorySeed(D.MIX, "Mono Compatible", "mono-compatible"),
    CategorySeed(D.MIX, "Dry Mix", "dry-mix"),
    CategorySeed(D.MIX, "Wet Mix", "wet-mix"),
    CategorySeed(D.MIX, "Bass Heavy", "bass-heavy"),
    CategorySeed(D.MIX, "Bright Mix", "bright-mix"),
    CategorySeed(D.MIX, "Dark Mix", "dark-mix"),
    CategorySeed(D.MIX, "Warm Mix", "warm-mix"),
    CategorySeed(D.MIX, "Punchy Mix", "punchy-mix"),
    CategorySeed(D.MIX, "Spacious Mix", "spacious-mix"),
    CategorySeed(D.MIX, "Intimate Mix", "intimate-mix"),
    CategorySeed(D.MIX, "Loud Mix", "loud-mix"),
    CategorySeed(D.MIX, "Dynamic Mix", "dynamic-mix"),
    CategorySeed(D.MIX, "Compressed Mix", "compressed-mix"),
    CategorySeed(D.MIX, "Lo-Fi Mix", "lo-fi-mix"),
    CategorySeed(D.MIX, "Hi-Fi Mix", "hi-fi-mix"),
    CategorySeed(D.MIX, "Centered Vocal", "centered-vocal"),
    CategorySeed(D.MIX, "Panned Vocal", "panned-vocal"),
    CategorySeed(D.MIX, "Double-Panned", "double-panned"),
    CategorySeed(D.MIX, "Drums Up Front", "drums-up-front"),
    CategorySeed(D.MIX, "Strings Back", "strings-back"),
    CategorySeed(D.MIX, "Sub-Heavy", "sub-heavy"),
    CategorySeed(D.MIX, "Mid-Forward", "mid-forward"),
    CategorySeed(D.MIX, "Air Band Boost", "air-band-boost"),
    CategorySeed(D.MIX, "Muddy Low-Mids", "muddy-low-mids"),
    CategorySeed(D.MIX, "Cinematic Depth", "cinematic-depth"),
)
