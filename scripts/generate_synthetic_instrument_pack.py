#!/usr/bin/env python3
"""Generate Synthetic Dark Bell v1 instrument pack for ACE LoRA training experiments.

80 deterministic 48 kHz stereo WAV clips with additive+FM bell synthesis,
exponential decay envelopes, sparse note patterns, noise shimmer, and simple reverb.
"""

from __future__ import annotations

import argparse
import array as _array
import hashlib
import json
import math
import random
import struct
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACK_NAME = "dark-bell-v1"
PACK_LABEL = "Synthetic Dark Bell v1"
DEFAULT_COUNT = 80
SAMPLE_RATE = 48000
CHANNELS = 2
GLOBAL_SEED = 20240101

CLIP_MIN_DURATION = 8.0
CLIP_MAX_DURATION = 15.0
MAX_PEAK = 0.72          # conservative normalization ceiling
SILENCE_FLOOR = 0.001   # envelope values below this terminate the note

# Bell partials: (frequency_ratio, initial_amplitude, per-sample decay factor base)
# Decay factors are computed at SAMPLE_RATE in _make_decay_factors()
_PARTIAL_RATIOS = [1.000, 2.000, 3.000, 4.100, 5.430]
_PARTIAL_AMPS   = [1.00,  0.55,  0.38,  0.27,  0.18]
_PARTIAL_DECAYS = [2.2,   3.8,   5.5,   8.0,   11.5]   # 1/tau in 1/sec

# Note frequencies (Hz) — 2+ octave span, dark low-register
_BASE_FREQS = [
    55.00, 61.74, 65.41, 73.42, 82.41, 87.31,
    98.00, 110.00, 123.47, 130.81, 146.83, 164.81,
    185.00, 196.00, 220.00,
]

_REGISTERS = {
    (55.0, 100.0): "deep",
    (100.0, 160.0): "mid",
    (160.0, 250.0): "high",
}

_CAPTION_TEMPLATES = [
    "sparse dark {register} bell {count} tone{s} with long metallic shimmer and quiet room decay",
    "deep {register} bell {count} strike{s} fading into metallic shimmer",
    "isolated {register} bell tone{s} in dark reverberant space with fm metallic resonance",
    "{count} dark bell {note_desc} dissolving into metallic noise shimmer",
    "sparse {register} bell strike{s} with inharmonic partials and sustained reverb tail",
    "slow dark bell motif — {count} note{s} — with exponential fade and room ambience",
    "{register} bell tone in sparse arrangement with fm metallic resonance",
]

_NOTE_DESCS = ["event", "events", "tone", "tones", "strike", "strikes", "impulse", "impulses"]


def _make_decay_factors() -> list[float]:
    dt = 1.0 / SAMPLE_RATE
    return [math.exp(-d * dt) for d in _PARTIAL_DECAYS]


_DECAY_FACTORS = _make_decay_factors()
_TWO_PI = 2.0 * math.pi


def _register_label(freq: float) -> str:
    for (lo, hi), label in _REGISTERS.items():
        if lo <= freq < hi:
            return label
    return "bell"


def _bell_note(freq: float, n_frames: int, rng: random.Random) -> list[float]:
    """Synthesize one bell strike via phase-accumulator additive+FM synthesis.

    Uses multiplicative envelope decay (no exp() per frame) and phase accumulators
    (no per-frame trig argument multiplication).
    """
    fm_ratio   = rng.uniform(0.85, 1.15)
    fm_index   = rng.uniform(1.2, 3.8)
    drift_rate = rng.uniform(0.04, 0.20)
    drift_depth = rng.uniform(0.001, 0.008)   # as fraction of base freq

    sr = SAMPLE_RATE
    dt = 1.0 / sr
    twopi = _TWO_PI

    # Phase increments (radians/sample) at base freq; drift adjusts instantaneously
    base_incs = [twopi * freq * r / sr for r in _PARTIAL_RATIOS]
    fm_inc_base = twopi * freq * fm_ratio / sr
    drift_inc = twopi * drift_rate / sr

    # Initial envelope amplitudes (will multiply per-sample decay factor)
    envs = list(_PARTIAL_AMPS)  # mutable copy
    decay_factors = _DECAY_FACTORS

    # Phase accumulators
    phases = [0.0] * len(_PARTIAL_RATIOS)
    fm_phase = 0.0
    drift_phase = 0.0

    _sin = math.sin
    buf: list[float] = [0.0] * n_frames

    for i in range(n_frames):
        # Drift modifies all frequencies proportionally
        drift_phase += drift_inc
        drift = 1.0 + drift_depth * _sin(drift_phase)

        # FM modulator
        fm_phase += fm_inc_base * drift
        mod = fm_index * _sin(fm_phase)

        # Accumulate partials
        s = 0.0
        for k in range(5):
            phases[k] += base_incs[k] * drift
            s += envs[k] * _sin(phases[k] + mod * (0.30 - k * 0.04))
            envs[k] *= decay_factors[k]

        buf[i] = s

        # Early exit when all partials are inaudible
        if envs[0] < SILENCE_FLOOR:
            break

    return buf


def _noise_shimmer(n_frames: int, level: float, rng: random.Random) -> list[float]:
    """High-passed Gaussian noise shimmer (first-order differencer)."""
    gauss = rng.gauss
    prev = 0.0
    buf: list[float] = [0.0] * n_frames
    for i in range(n_frames):
        x = gauss(0.0, 1.0)
        # High-pass via first difference (H(z) = 0.5*(1 - z^{-1}))
        y = (x - prev) * 0.5 * level
        prev = x
        buf[i] = y
    return buf


def _apply_reverb(buf: list[float], room: float) -> list[float]:
    """In-place feed-forward comb reverb (3 taps). room in [0..1]."""
    n = len(buf)
    delays = (1499, 2003, 2731)
    gains  = (0.18 * room, 0.13 * room, 0.09 * room)
    for delay, gain in zip(delays, gains):
        for i in range(delay, n):
            buf[i] += buf[i - delay] * gain
    return buf


def _mix_stereo(mono: list[float], delay_samples: int = 73) -> tuple[list[float], list[float]]:
    """Create stereo pair from mono with a tiny cross-delay on the right channel."""
    n = len(mono)
    left = mono
    right = [0.0] * n
    for i in range(n):
        right[i] = mono[i - delay_samples] if i >= delay_samples else 0.0
    return left, right


def _normalize(buf: list[float], peak: float = MAX_PEAK) -> list[float]:
    max_abs = max(abs(s) for s in buf) if buf else 1.0
    if max_abs < 1e-9:
        return buf
    scale = peak / max_abs
    return [s * scale for s in buf]


def _to_int16(samples: list[float]) -> _array.array:
    """Clamp and quantize to signed 16-bit PCM."""
    out = _array.array("h")
    for s in samples:
        v = int(s * 32767.0)
        if v > 32767:
            v = 32767
        elif v < -32767:
            v = -32767
        out.append(v)
    return out


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_clip(
    clip_idx: int,
    rng: random.Random,
    *,
    min_dur: float = CLIP_MIN_DURATION,
    max_dur: float = CLIP_MAX_DURATION,
) -> tuple[list[float], list[float], dict[str, Any]]:
    """Synthesize one stereo clip. Returns (left, right, params_dict)."""
    duration = rng.uniform(min_dur, max_dur)
    n_frames = int(duration * SAMPLE_RATE)
    n_notes = rng.randint(2, 5)
    room = rng.uniform(0.25, 0.65)
    shimmer_level = rng.uniform(0.02, 0.08) if rng.random() < 0.7 else 0.0

    # Pick base frequency for this clip
    base_freq = rng.choice(_BASE_FREQS)

    # Note onsets: spread across first 70% of clip, minimum 1 s apart
    max_onset = duration * 0.70
    onsets: list[float] = []
    for _ in range(n_notes * 10):
        if len(onsets) >= n_notes:
            break
        t = rng.uniform(0.05, max_onset)
        if all(abs(t - o) >= 1.0 for o in onsets):
            onsets.append(t)
    onsets.sort()
    if not onsets:
        onsets = [rng.uniform(0.05, duration * 0.5)]

    # Build mono buffer
    mono: list[float] = [0.0] * n_frames

    note_events: list[dict] = []
    for onset in onsets:
        # Each note gets its own RNG seeded from the clip RNG — keeps everything
        # reproducible while letting note params vary independently.
        note_seed = rng.randint(0, 2**31)
        note_rng = random.Random(note_seed)

        freq = base_freq * (2.0 ** note_rng.uniform(-0.04, 0.04))
        onset_frame = int(onset * SAMPLE_RATE)
        remaining = n_frames - onset_frame
        if remaining <= 0:
            continue

        note_buf = _bell_note(freq, remaining, note_rng)

        for j, s in enumerate(note_buf):
            mono[onset_frame + j] += s

        note_events.append({
            "onset_s": round(onset, 4),
            "freq_hz": round(freq, 3),
            "note_seed": note_seed,
        })

    # Noise shimmer
    if shimmer_level > 0.0:
        shimmer = _noise_shimmer(n_frames, shimmer_level, rng)
        for i in range(n_frames):
            mono[i] += shimmer[i]

    # Reverb
    mono = _apply_reverb(mono, room)

    # Normalize
    mono = _normalize(mono)

    # Stereo
    stereo_delay = rng.randint(48, 120)   # 1–2.5 ms
    left, right = _mix_stereo(mono, stereo_delay)

    params: dict[str, Any] = {
        "duration_seconds": round(duration, 4),
        "base_freq_hz": round(base_freq, 3),
        "note_count": len(onsets),
        "note_events": note_events,
        "room_size": round(room, 4),
        "shimmer_level": round(shimmer_level, 4),
        "stereo_delay_samples": stereo_delay,
    }
    return left, right, params


def write_wav(path: Path, left: list[float], right: list[float]) -> None:
    """Write 48 kHz stereo 16-bit PCM WAV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = min(len(left), len(right))
    # Interleave L/R
    interleaved = _array.array("h")
    for i in range(n):
        lv = int(left[i] * 32767.0)
        rv = int(right[i] * 32767.0)
        interleaved.append(max(-32767, min(32767, lv)))
        interleaved.append(max(-32767, min(32767, rv)))

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(interleaved.tobytes())


def _build_caption(params: dict, clip_idx: int, rng: random.Random) -> str:
    count = params["note_count"]
    base_freq = params["base_freq_hz"]
    reg = _register_label(base_freq)
    s = "" if count == 1 else "s"
    note_desc = rng.choice(_NOTE_DESCS)
    if note_desc.endswith("s"):
        note_desc = note_desc[:-1] if count == 1 else note_desc
    else:
        note_desc = note_desc if count == 1 else note_desc + "s"

    tmpl = _CAPTION_TEMPLATES[clip_idx % len(_CAPTION_TEMPLATES)]
    return tmpl.format(
        register=reg,
        count=count,
        s=s,
        note_desc=note_desc,
    ).strip()


def generate_pack(
    output_dir: Path,
    count: int = DEFAULT_COUNT,
    global_seed: int = GLOBAL_SEED,
    *,
    min_dur: float = CLIP_MIN_DURATION,
    max_dur: float = CLIP_MAX_DURATION,
    verbose: bool = True,
) -> list[dict[str, Any]]:
    """Generate all clips and write metadata.jsonl. Returns list of metadata rows."""
    output_dir.mkdir(parents=True, exist_ok=True)
    master_rng = random.Random(global_seed)

    rows: list[dict[str, Any]] = []
    for idx in range(1, count + 1):
        clip_seed = master_rng.randint(0, 2**32 - 1)
        clip_rng = random.Random(clip_seed)
        caption_rng = random.Random(clip_seed ^ 0xDEADBEEF)

        left, right, params = generate_clip(idx, clip_rng, min_dur=min_dur, max_dur=max_dur)

        filename = f"{PACK_NAME}-{idx:03d}.wav"
        wav_path = output_dir / filename
        write_wav(wav_path, left, right)

        file_hash = _sha256(wav_path)
        caption = _build_caption(params, idx - 1, caption_rng)

        row: dict[str, Any] = {
            "file_path": str(wav_path),
            "seed": clip_seed,
            "duration": params["duration_seconds"],
            "synthesis_params": params,
            "caption": caption,
            "tags": ["synthetic", "bell", "metallic", "ambient", "sparse", "dark"],
            "sha256": file_hash,
            "sample_rate": SAMPLE_RATE,
            "channels": CHANNELS,
            "pack": PACK_NAME,
            "clip_index": idx,
        }
        rows.append(row)

        if verbose:
            print(f"  [{idx:3d}/{count}] {filename}  {params['duration_seconds']:.1f}s  "
                  f"{params['note_count']} notes  {caption[:60]}")

    meta_path = output_dir / "metadata.jsonl"
    with meta_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")

    if verbose:
        print(f"\nWrote {count} clips and metadata.jsonl → {output_dir}")

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Synthetic Dark Bell v1 instrument pack")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Output directory (default: data/synthetic_audio/dark-bell-v1)")
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT,
                        help=f"Number of clips to generate (default: {DEFAULT_COUNT})")
    parser.add_argument("--seed", type=int, default=GLOBAL_SEED,
                        help=f"Global RNG seed (default: {GLOBAL_SEED})")
    parser.add_argument("--min-dur", type=float, default=CLIP_MIN_DURATION)
    parser.add_argument("--max-dur", type=float, default=CLIP_MAX_DURATION)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    output_dir = args.output_dir or (root / "data" / "synthetic_audio" / PACK_NAME)

    generate_pack(
        output_dir,
        count=args.count,
        global_seed=args.seed,
        min_dur=args.min_dur,
        max_dur=args.max_dur,
        verbose=not args.quiet,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
