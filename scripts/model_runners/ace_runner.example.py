#!/usr/bin/env python3
"""Stable ACE-Step runner contract used by the AI Music POC.

Copy this file outside the app, for example:

    ~/models/ace_runner.py

Then edit `run_ace_step()` to call the real ACE-Step inference code or CLI from
whichever ACE-Step checkout you installed. Keep this wrapper's arguments stable
so the web app does not need to change when ACE internals change.

This example includes a --dry-run mode and a tiny placeholder WAV writer so you
can validate command wiring before real model integration. Do not confuse the
placeholder WAV with ACE output.
"""
from __future__ import annotations

import argparse
import math
import os
import wave
from pathlib import Path


def read_text(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8", errors="replace")


def write_placeholder_wav(path: Path, duration_seconds: int = 3, sample_rate: int = 44100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = bytearray()
    for i in range(duration_seconds * sample_rate):
        t = i / sample_rate
        env = min(1.0, i / (sample_rate * 0.05)) * min(1.0, (duration_seconds * sample_rate - i) / (sample_rate * 0.1))
        value = int(9000 * env * math.sin(2 * math.pi * 220 * t))
        frames += value.to_bytes(2, "little", signed=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(frames))


def run_ace_step(args: argparse.Namespace) -> None:
    prompt = read_text(args.prompt_file) or args.prompt or ""
    lyrics = read_text(args.lyrics_file)
    negative = read_text(args.negative_file)

    # Replace this block with the real ACE-Step call for your checkout.
    # Example shape only:
    #   from acestep.pipeline import ACEStepPipeline
    #   pipe = ACEStepPipeline(checkpoint_dir=args.model_dir, device=args.device)
    #   pipe.generate(
    #       prompt=prompt,
    #       lyrics=lyrics,
    #       negative_prompt=negative,
    #       audio_duration=args.duration,
    #       seed=args.seed,
    #       guidance_scale=args.guidance_scale,
    #       output_path=args.output,
    #   )
    if args.dry_run:
        print("ACE runner dry-run ok")
        print(f"prompt chars={len(prompt)} lyrics chars={len(lyrics)} negative chars={len(negative)}")
        print(f"voice={args.singing_voice} intensity={args.vocal_intensity} style={args.vocal_style}")
        print(f"HF_HOME={os.environ.get('HF_HOME', '')}")
        return

    if args.placeholder_wav:
        write_placeholder_wav(Path(args.output), min(args.duration, 5))
        print(f"placeholder wav written to {args.output}")
        return

    raise SystemExit(
        "ace_runner.example.py is only a wrapper template. Copy it to ~/models/ace_runner.py "
        "and replace run_ace_step() with the real ACE-Step inference call."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stable ACE-Step runner wrapper for AI Music POC")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--prompt-file")
    parser.add_argument("--lyrics-file")
    parser.add_argument("--negative-file")
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--guidance-scale", type=float, default=7.5)
    parser.add_argument("--quality", default="draft")
    parser.add_argument("--singing-voice", default="auto")
    parser.add_argument("--vocal-intensity", type=float, default=0.65)
    parser.add_argument("--vocal-style", default="")
    parser.add_argument("--model-dir", default="")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--dry-run", action="store_true", help="Validate wiring without running ACE-Step inference")
    parser.add_argument("--placeholder-wav", action="store_true", help="Write a tiny fake WAV only to test app wiring")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.dry_run:
        print("ACE runner dry-run ok")
        print(f"prompt_file={args.prompt_file} lyrics_file={args.lyrics_file}")
        print(f"voice={args.singing_voice} intensity={args.vocal_intensity} style={args.vocal_style!r}")
        raise SystemExit(0)
    run_ace_step(args)
