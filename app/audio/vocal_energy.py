from __future__ import annotations

import struct
import wave
from dataclasses import dataclass
from pathlib import Path

from app.generators.vocal_plan import VocalPlan


@dataclass(frozen=True)
class EnergyWindow:
    label: str
    kind: str
    rms: float
    beat_start: float
    beat_end: float


def read_mono_wav_normalized(path: Path) -> tuple[list[float], int]:
    with wave.open(str(path), "rb") as wav:
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        frames = wav.readframes(wav.getnframes())
    samples = struct.unpack(f"<{len(frames) // 2}h", frames)
    if channels == 2:
        mono = [(samples[index] + samples[index + 1]) / 2.0 for index in range(0, len(samples), 2)]
    else:
        mono = [float(sample) for sample in samples]
    return [sample / 32768.0 for sample in mono], sample_rate


def _beat_slice(samples: list[float], sample_rate: int, bpm: int, beat_start: float, beat_end: float) -> list[float]:
    seconds_per_beat = 60.0 / bpm
    start = max(0, int(beat_start * seconds_per_beat * sample_rate))
    end = min(len(samples), int(beat_end * seconds_per_beat * sample_rate))
    return samples[start:end]


def _rms(chunk: list[float]) -> float:
    if not chunk:
        return 0.0
    return (sum(sample * sample for sample in chunk) / len(chunk)) ** 0.5


def plan_energy_windows(plan: VocalPlan, samples: list[float], sample_rate: int) -> list[EnergyWindow]:
    windows: list[EnergyWindow] = []
    for section in plan.sections:
        for line in section.lines:
            for syllable in line.syllables:
                inner_start = syllable.beat_start + syllable.beat_duration * 0.25
                inner_end = syllable.beat_start + syllable.beat_duration * 0.75
                chunk = _beat_slice(samples, sample_rate, plan.bpm, inner_start, inner_end)
                windows.append(
                    EnergyWindow(
                        label=f"{section.name}:{syllable.text}",
                        kind="syllable",
                        rms=_rms(chunk),
                        beat_start=inner_start,
                        beat_end=inner_end,
                    )
                )
            if line.rest_beats_after > 0 and line.syllables:
                last = line.syllables[-1]
                rest_start = last.beat_start + last.beat_duration
                rest_mid = rest_start + line.rest_beats_after * 0.5
                rest_half = line.rest_beats_after * 0.3
                chunk = _beat_slice(samples, sample_rate, plan.bpm, rest_mid - rest_half, rest_mid + rest_half)
                windows.append(
                    EnergyWindow(
                        label=f"{section.name}:rest",
                        kind="rest",
                        rms=_rms(chunk),
                        beat_start=rest_start,
                        beat_end=rest_start + line.rest_beats_after,
                    )
                )
    return windows


def max_abs_sample(samples: list[float]) -> float:
    return max((abs(sample) for sample in samples), default=0.0)


def assert_vocal_stem_timing(
    plan: VocalPlan,
    stem_path: Path,
    *,
    syllable_rms_min: float = 0.0035,
    rest_rms_max: float = 0.0025,
    rest_to_syllable_max_ratio: float = 0.35,
) -> dict[str, float]:
    samples, sample_rate = read_mono_wav_normalized(stem_path)
    if max_abs_sample(samples) > 1.0:
        raise AssertionError(f"vocal stem clips: peak={max_abs_sample(samples):.4f}")

    windows = plan_energy_windows(plan, samples, sample_rate)
    syllable_windows = [window for window in windows if window.kind == "syllable"]
    rest_windows = [window for window in windows if window.kind == "rest"]
    if not syllable_windows:
        raise AssertionError("no syllable windows to measure")

    syllable_median = sorted(window.rms for window in syllable_windows)[len(syllable_windows) // 2]
    low_syllables = [window for window in syllable_windows if window.rms < syllable_rms_min]
    if low_syllables:
        labels = ", ".join(window.label for window in low_syllables[:3])
        raise AssertionError(f"syllable windows too quiet: {labels}")

    loud_rests = [
        window
        for window in rest_windows
        if window.rms > rest_rms_max and window.rms > syllable_median * rest_to_syllable_max_ratio
    ]
    if loud_rests:
        labels = ", ".join(window.label for window in loud_rests[:3])
        raise AssertionError(f"rest windows still vocalized: {labels}")

    return {
        "syllable_median_rms": syllable_median,
        "rest_max_rms": max((window.rms for window in rest_windows), default=0.0),
        "peak": max_abs_sample(samples),
    }
