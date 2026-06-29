from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from app.generators.svs.models import SvsScore
from app.generators.vocal_plan import midi_to_hz

SAMPLE_RATE = 44_100


def _envelope(position: float, total: int) -> float:
    if total <= 0:
        return 0.0
    x = position / total
    attack = min(0.08, 0.35 / max(total, 1))
    release = min(0.12, 0.40 / max(total, 1))
    if x < attack:
        return x / max(attack, 1e-6)
    if x > 1.0 - release:
        return max(0.0, (1.0 - x) / max(release, 1e-6))
    return 1.0


def render_score_to_wav(score: SvsScore, output_path: Path, *, amplitude: float = 0.35) -> None:
    total_seconds = score.duration_beats * 60.0 / score.bpm
    total_samples = max(1, int(total_seconds * SAMPLE_RATE))
    samples = [0.0] * total_samples
    seconds_per_beat = 60.0 / score.bpm

    for event in score.note_events():
        start = int(event.start_beats * seconds_per_beat * SAMPLE_RATE)
        end = int((event.start_beats + event.duration_beats) * seconds_per_beat * SAMPLE_RATE)
        end = min(total_samples, max(start + 1, end))
        hz = midi_to_hz(event.midi)
        gain = amplitude * (1.15 if event.stressed else 1.0)
        length = end - start
        for offset in range(length):
            t = (start + offset) / SAMPLE_RATE
            wave_sample = math.sin(2.0 * math.pi * hz * t)
            samples[start + offset] += wave_sample * gain * _envelope(offset, length)

    peak = max((abs(sample) for sample in samples), default=0.0)
    if peak > 0.98:
        scale = 0.98 / peak
        samples = [sample * scale for sample in samples]

    frames = bytearray()
    for sample in samples:
        clipped = max(-1.0, min(1.0, sample))
        frames.extend(struct.pack("<h", int(clipped * 32_767)))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(frames))
