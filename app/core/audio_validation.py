from __future__ import annotations

import math
import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AudioValidationResult:
    ok: bool
    path: Path
    file_size_bytes: int
    duration_seconds: float
    sample_rate: int
    channels: int
    sample_width_bytes: int
    peak_abs_sample: int
    rms: float
    warnings: list[str]


def validate_wav_output(path: Path, expected_duration_seconds: int | None = None, min_size_bytes: int = 4096) -> AudioValidationResult:
    warnings: list[str] = []
    if not path.exists():
        raise RuntimeError(f"Expected audio output was not created: {path}")
    file_size = path.stat().st_size
    if file_size < min_size_bytes:
        raise RuntimeError(f"Audio output is too small to be valid: {file_size} bytes")

    try:
        with wave.open(str(path), "rb") as handle:
            channels = handle.getnchannels()
            sample_rate = handle.getframerate()
            sample_width = handle.getsampwidth()
            frame_count = handle.getnframes()
            duration = frame_count / float(sample_rate or 1)
            sample_bytes = handle.readframes(min(frame_count, sample_rate * 10))
    except wave.Error as exc:
        raise RuntimeError(f"Audio output is not a readable WAV file: {exc}") from exc

    if channels < 1:
        raise RuntimeError("Audio output has no channels")
    if sample_rate < 8000:
        warnings.append(f"Unexpectedly low sample rate: {sample_rate}")
    if duration <= 0:
        raise RuntimeError("Audio output has zero duration")
    if expected_duration_seconds is not None:
        lower = max(1.0, expected_duration_seconds * 0.5)
        upper = expected_duration_seconds * 1.8 + 2
        if duration < lower or duration > upper:
            warnings.append(f"Duration {duration:.2f}s differs from requested {expected_duration_seconds}s")

    peak = _peak_abs_sample(sample_bytes, sample_width)
    rms = _rms_sample(sample_bytes, sample_width)
    if peak == 0 or rms <= 0.1:
        raise RuntimeError("Audio output appears to be silent")

    return AudioValidationResult(
        ok=True,
        path=path,
        file_size_bytes=file_size,
        duration_seconds=round(duration, 3),
        sample_rate=sample_rate,
        channels=channels,
        sample_width_bytes=sample_width,
        peak_abs_sample=peak,
        rms=round(rms, 3),
        warnings=warnings,
    )


def _peak_abs_sample(data: bytes, sample_width: int) -> int:
    if not data:
        return 0
    if sample_width == 1:
        return max(abs(byte - 128) for byte in data)
    if sample_width == 2:
        peak = 0
        for index in range(0, len(data) - 1, 2):
            value = int.from_bytes(data[index:index + 2], "little", signed=True)
            peak = max(peak, abs(value))
        return peak
    # Conservative fallback for 24/32-bit PCM. It is enough for silence detection.
    step = sample_width
    peak = 0
    for index in range(0, len(data) - step + 1, step):
        value = int.from_bytes(data[index:index + step], "little", signed=True)
        peak = max(peak, abs(value))
    return peak


def _rms_sample(data: bytes, sample_width: int) -> float:
    if not data:
        return 0.0
    values: list[int] = []
    if sample_width == 1:
        values = [byte - 128 for byte in data[:200_000]]
    else:
        step = sample_width
        for index in range(0, min(len(data), 400_000) - step + 1, step):
            values.append(int.from_bytes(data[index:index + step], "little", signed=True))
    if not values:
        return 0.0
    return math.sqrt(sum(value * value for value in values) / len(values))
