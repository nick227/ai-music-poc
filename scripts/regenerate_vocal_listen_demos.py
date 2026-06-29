#!/usr/bin/env python3
"""Regenerate vocal-plan listen-test WAVs for manual QA."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.domain.models import GenerationRequest
from app.generators.procedural import ProceduralGenerator

DEFAULT_OUTPUT_DIR = Path("data/experiments/vocal-plan-v01")

DEMO_CASES: tuple[tuple[str, str, str], ...] = (
    (
        "pop_chorus",
        "bright pop chorus hook glossy drums",
        """Verse:
I walk alone beneath the city lights
Chorus:
We rise tonight we shine so bright""",
    ),
    (
        "rap_dense",
        "heavy rap mixtape hard 808 drums",
        "Verse:\nSpitting rapid fire syllables never miss a beat on the street",
    ),
    (
        "ballad_held",
        "acoustic ballad piano soft drums",
        "Verse:\nHold me close until the night turns into dawn",
    ),
)


def resolve_output_dir(output_dir: Path, timestamped: bool) -> Path:
    if timestamped:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return output_dir / stamp
    return output_dir


def regenerate_cases(
    output_dir: Path,
    *,
    duration_seconds: int = 14,
    quality: str = "draft",
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generator = ProceduralGenerator()
    written: list[Path] = []
    for name, prompt, lyrics in DEMO_CASES:
        request = GenerationRequest.model_validate(
            {
                "title": name,
                "prompt": prompt,
                "lyrics": lyrics,
                "duration_seconds": duration_seconds,
                "quality": quality,
                "mode": "song",
                "vocal_intensity": 0.65,
                "vocal_style": "ballad held legato" if name == "ballad_held" else None,
                "seed": 42,
            }
        )
        wav_path = output_dir / f"{name}.wav"
        generator.generate(request, wav_path)
        written.append(wav_path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Base directory for listen-test WAV outputs",
    )
    parser.add_argument(
        "--timestamped",
        action="store_true",
        help="Write into a UTC timestamp subdirectory instead of overwriting stable filenames",
    )
    parser.add_argument(
        "--quality",
        choices=("draft", "balanced", "high"),
        default="draft",
        help="Procedural quality (draft = timing preview; not ACE/neural music)",
    )
    args = parser.parse_args()
    target_dir = resolve_output_dir(args.output_dir.expanduser().resolve(), args.timestamped)
    paths = regenerate_cases(target_dir, quality=args.quality)
    print("Note: procedural draft previews validate VocalPlan timing, not final music quality.")
    print("Use balanced/high + ACE-Step in the app for listenable songs.")
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
