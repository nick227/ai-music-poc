import math
import wave

import pytest

from app.core.audio_validation import validate_wav_output


def write_wav(path, seconds=1, sample_rate=44100, silent=False):
    frames = bytearray()
    for i in range(seconds * sample_rate):
        value = 0 if silent else int(8000 * math.sin(2 * math.pi * 220 * (i / sample_rate)))
        frames += value.to_bytes(2, 'little', signed=True)
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(frames))


def test_validate_wav_output_accepts_real_wav(tmp_path):
    path = tmp_path / 'ok.wav'
    write_wav(path)
    result = validate_wav_output(path, expected_duration_seconds=1)
    assert result.ok is True
    assert result.sample_rate == 44100
    assert result.peak_abs_sample > 0


def test_validate_wav_output_rejects_silence(tmp_path):
    path = tmp_path / 'silent.wav'
    write_wav(path, silent=True)
    with pytest.raises(RuntimeError, match='silent'):
        validate_wav_output(path)
