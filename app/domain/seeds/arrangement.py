from __future__ import annotations

from app.domain.enums import CategoryDimension as D
from app.domain.seeds._core import CategorySeed

ARRANGEMENT_SEEDS: tuple[CategorySeed, ...] = (
    CategorySeed(D.ARRANGEMENT, "Sparse", "sparse"),
    CategorySeed(D.ARRANGEMENT, "Dense", "dense"),
    CategorySeed(D.ARRANGEMENT, "Layered", "layered"),
    CategorySeed(D.ARRANGEMENT, "Minimal", "minimal"),
    CategorySeed(D.ARRANGEMENT, "Full Band", "full-band"),
    CategorySeed(D.ARRANGEMENT, "Solo Performance", "solo-performance"),
    CategorySeed(D.ARRANGEMENT, "Duo", "duo"),
    CategorySeed(D.ARRANGEMENT, "Trio", "trio"),
    CategorySeed(D.ARRANGEMENT, "Quartet", "quartet"),
    CategorySeed(D.ARRANGEMENT, "Orchestral", "orchestral"),
    CategorySeed(D.ARRANGEMENT, "Chamber", "chamber"),
    CategorySeed(D.ARRANGEMENT, "Acoustic Unplugged", "acoustic-unplugged"),
    CategorySeed(D.ARRANGEMENT, "Electronic Only", "electronic-only"),
    CategorySeed(D.ARRANGEMENT, "Hybrid Acoustic-Electronic", "hybrid-acoustic-electronic"),
    CategorySeed(D.ARRANGEMENT, "Intro-Build-Drop", "intro-build-drop"),
    CategorySeed(D.ARRANGEMENT, "Verse-Chorus", "verse-chorus"),
    CategorySeed(D.ARRANGEMENT, "Through-Composed", "through-composed"),
    CategorySeed(D.ARRANGEMENT, "Loop-Based", "loop-based"),
    CategorySeed(D.ARRANGEMENT, "Call and Response Arrangement", "call-and-response-arrangement"),
    CategorySeed(D.ARRANGEMENT, "Antiphonal", "antiphonal"),
    CategorySeed(D.ARRANGEMENT, "Stems-Ready", "stems-ready"),
    CategorySeed(D.ARRANGEMENT, "Vocal-Led", "vocal-led"),
    CategorySeed(D.ARRANGEMENT, "Instrumental-Led", "instrumental-led"),
    CategorySeed(D.ARRANGEMENT, "Ambient Bed", "ambient-bed"),
    CategorySeed(D.ARRANGEMENT, "Stripped Down", "stripped-down"),
    CategorySeed(D.ARRANGEMENT, "Big Finish", "big-finish"),
    CategorySeed(D.ARRANGEMENT, "Fade Out", "fade-out"),
    CategorySeed(D.ARRANGEMENT, "Dynamic Contrast", "dynamic-contrast"),
    CategorySeed(D.ARRANGEMENT, "Textural Shift", "textural-shift"),
    CategorySeed(D.ARRANGEMENT, "Bridge Section", "bridge-section"),
)
