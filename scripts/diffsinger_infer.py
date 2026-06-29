#!/usr/bin/env python3
"""
DiffSinger ONNX inference for TIGER v106-style voice packs.
Reads a .ds JSON file (DiffSinger segment format) and produces a WAV file.

Usage:
  export LD_LIBRARY_PATH=/path/to/nvidia-cu13/lib:/path/to/cudnn/lib:$LD_LIBRARY_PATH
  python scripts/diffsinger_infer.py \\
    --ds data/experiments/svs-diffsinger-v01/pop_chorus_stem.ds \\
    --output data/experiments/svs-diffsinger-v01/pop_chorus_stem.wav \\
    --tiger-dir /home/administrator/web/diffsinger-env/tiger \\
    --speaker tiger_fresh
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

HOP_SIZE = 512
SAMPLE_RATE = 44100
FRAMES_PER_SEC = SAMPLE_RATE / HOP_SIZE  # ≈ 86.13 fps

_NOTE_SEMITONES = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


def _note_to_midi(note: str) -> int:
    if note in ("rest", "SP"):
        return 0
    for key in sorted(_NOTE_SEMITONES, key=len, reverse=True):
        if note.startswith(key):
            return (int(note[len(key):]) + 1) * 12 + _NOTE_SEMITONES[key]
    raise ValueError(f"Cannot parse note name: {note!r}")


def _midi_to_f0(midi: int) -> float:
    return 440.0 * (2.0 ** ((midi - 69) / 12.0)) if midi > 0 else 0.0


def load_phoneme_map(path: Path) -> dict[str, int]:
    phonemes: dict[str, int] = {}
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        ph = line.strip()
        if ph:
            phonemes[ph] = i
    return phonemes


def load_speaker_embed(path: Path) -> np.ndarray:
    data = path.read_bytes()
    n = len(data) // 4
    return np.array(struct.unpack(f"{n}f", data[:n * 4]), dtype=np.float32)


def ds_to_inputs(
    segments: list[dict],
    phoneme_map: dict[str, int],
    spk_embed: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Convert .ds segments to acoustic model input arrays."""
    all_tokens: list[int] = []
    all_durations: list[int] = []
    all_f0: list[float] = []

    sp_idx = phoneme_map.get("SP", 2)

    for seg in segments:
        ph_list = seg["ph_seq"].split()
        ph_dur_secs = [float(x) for x in seg["ph_dur"].split()]
        note_list = seg["note_seq"].split()
        note_dur_secs = [float(x) for x in seg["note_dur"].split()]
        ph_num_list = [int(x) for x in seg["ph_num"].split()]

        # Phoneme indices — CMU ARPAbet → lowercase for TIGER
        for ph in ph_list:
            tiger_ph = ph if ph in ("AP", "SP", "<PAD>") else ph.lower()
            all_tokens.append(phoneme_map.get(tiger_ph, sp_idx))

        # Duration in frames per phoneme
        ph_frames = [max(1, int(round(d * FRAMES_PER_SEC))) for d in ph_dur_secs]
        all_durations.extend(ph_frames)

        # F0 per frame, derived from note MIDI
        ph_cursor = 0
        for note_name, note_ph_count in zip(note_list, ph_num_list):
            midi = _note_to_midi(note_name)
            f0_val = _midi_to_f0(midi)
            note_frames = sum(ph_frames[ph_cursor: ph_cursor + note_ph_count])
            all_f0.extend([f0_val] * note_frames)
            ph_cursor += note_ph_count

    n_frames = sum(all_durations)
    # Trim/pad f0 to exactly n_frames
    if len(all_f0) < n_frames:
        all_f0.extend([0.0] * (n_frames - len(all_f0)))
    else:
        all_f0 = all_f0[:n_frames]

    tokens_arr = np.array(all_tokens, dtype=np.int64)[np.newaxis, :]
    durations_arr = np.array(all_durations, dtype=np.int64)[np.newaxis, :]
    f0_arr = np.array(all_f0, dtype=np.float32)[np.newaxis, :]
    spk_arr = np.tile(spk_embed[np.newaxis, np.newaxis, :], (1, n_frames, 1)).astype(np.float32)

    return tokens_arr, durations_arr, f0_arr, spk_arr


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ds", type=Path, required=True, help=".ds JSON input")
    parser.add_argument("--output", type=Path, required=True, help="Output WAV path")
    parser.add_argument("--tiger-dir", type=Path, required=True, help="Extracted TIGER directory")
    parser.add_argument(
        "--speaker",
        default="tiger_fresh",
        choices=["tiger_fresh", "tiger_disco", "tiger_electric",
                 "tiger_vinyl", "tiger_glam", "tiger_mystic", "tiger_royal"],
    )
    parser.add_argument("--depth", type=float, default=0.6, help="Diffusion depth 0.0–1.0")
    parser.add_argument("--steps", type=int, default=20, help="Diffusion steps")
    args = parser.parse_args()

    import onnxruntime as ort  # noqa: PLC0415 — import inside main to respect LD_LIBRARY_PATH

    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]

    acou_opts = ort.SessionOptions()
    acou_opts.log_severity_level = 3
    # Disable all graph optimizations — the acoustic model crashes ort's optimizer.
    acou_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL

    tiger_dir = args.tiger_dir.expanduser().resolve()
    acoustic_dir = tiger_dir / "dsacoustic"
    vocoder_dir = tiger_dir / "dsvocoder"

    print("Loading acoustic model (327 MB)…")
    acoustic_sess = ort.InferenceSession(
        str(acoustic_dir / "acoustic.onnx"),
        sess_options=acou_opts,
        providers=providers,
    )

    print("Loading vocoder…")
    vocoder_sess = ort.InferenceSession(
        str(vocoder_dir / "tgm_hifigan.onnx"),
        providers=providers,
    )

    phoneme_map = load_phoneme_map(acoustic_dir / "phonemes.txt")
    spk_embed = load_speaker_embed(acoustic_dir / f"{args.speaker}.emb")

    ds_segments = json.loads(args.ds.read_text(encoding="utf-8"))
    tokens, durations, f0, spk_expanded = ds_to_inputs(ds_segments, phoneme_map, spk_embed)

    n_tokens = tokens.shape[1]
    n_frames = f0.shape[1]
    print(f"Acoustic: {n_tokens} phonemes, {n_frames} frames "
          f"({n_frames / FRAMES_PER_SEC:.1f}s), depth={args.depth}, steps={args.steps}")

    mel = acoustic_sess.run(
        ["mel"],
        {
            "tokens": tokens,
            "durations": durations,
            "f0": f0,
            "gender": np.zeros_like(f0),
            "velocity": np.zeros_like(f0),
            "spk_embed": spk_expanded,
            "depth": np.array(args.depth, dtype=np.float32),
            "steps": np.array(args.steps, dtype=np.int64),
        },
    )[0]

    print(f"Vocoder: mel {mel.shape}…")
    waveform = vocoder_sess.run(["waveform"], {"mel": mel, "f0": f0})[0]

    audio = waveform[0]  # [n_samples]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(args.output), audio, SAMPLE_RATE)
    duration_sec = len(audio) / SAMPLE_RATE
    print(f"Saved: {args.output}  ({duration_sec:.2f}s @ {SAMPLE_RATE} Hz)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
