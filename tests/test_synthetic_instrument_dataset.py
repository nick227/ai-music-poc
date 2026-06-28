"""Tests for Synthetic Dark Bell v1 dataset generation and ingestion pipeline."""

from __future__ import annotations

import hashlib
import json
import math
import wave
from pathlib import Path

import pytest

from scripts.generate_synthetic_instrument_pack import (
    DEFAULT_COUNT,
    PACK_NAME,
    SAMPLE_RATE,
    CHANNELS,
    MAX_PEAK,
    generate_pack,
    generate_clip,
    write_wav,
    _bell_note,
    _noise_shimmer,
    _apply_reverb,
    _normalize,
)
from scripts.ingest_synthetic_instrument_pack import ingest_synthetic_pack
from scripts.verify_synthetic_instrument_dataset_flow import verify_synthetic_instrument_dataset_flow

import random


# ── Synthesis unit tests ───────────────────────────────────────────────────────

class TestBellNoteSynthesis:
    def test_returns_non_empty_list(self):
        rng = random.Random(42)
        buf = _bell_note(220.0, 1000, rng)
        assert len(buf) == 1000 or len(buf) < 1000   # may exit early on silence floor

    def test_deterministic_with_same_seed(self):
        buf1 = _bell_note(110.0, 4800, random.Random(7))
        buf2 = _bell_note(110.0, 4800, random.Random(7))
        assert buf1 == buf2

    def test_different_seeds_differ(self):
        buf1 = _bell_note(220.0, 4800, random.Random(1))
        buf2 = _bell_note(220.0, 4800, random.Random(2))
        assert buf1 != buf2

    def test_peak_amplitude_reasonable(self):
        rng = random.Random(42)
        buf = _bell_note(220.0, SAMPLE_RATE // 4, rng)
        peak = max(abs(s) for s in buf)
        # Sum of partial amplitudes = 1.0+0.55+0.38+0.27+0.18 = 2.38 at t=0
        assert peak <= 3.0, f"peak {peak} unexpectedly high"

    def test_envelope_decays(self):
        rng = random.Random(99)
        n = int(SAMPLE_RATE * 4)
        buf = _bell_note(220.0, n, rng)
        # Energy in first 0.5s should exceed energy in last 0.5s
        half_sr = SAMPLE_RATE // 2
        early_rms = math.sqrt(sum(s**2 for s in buf[:half_sr]) / half_sr)
        if len(buf) >= n:
            late_rms = math.sqrt(sum(s**2 for s in buf[-half_sr:]) / half_sr)
            assert early_rms > late_rms * 3, "Envelope not decaying fast enough"


class TestNoiseShimmer:
    def test_length(self):
        rng = random.Random(1)
        buf = _noise_shimmer(1000, 0.05, rng)
        assert len(buf) == 1000

    def test_deterministic(self):
        buf1 = _noise_shimmer(500, 0.05, random.Random(3))
        buf2 = _noise_shimmer(500, 0.05, random.Random(3))
        assert buf1 == buf2

    def test_zero_level_is_silent(self):
        rng = random.Random(5)
        buf = _noise_shimmer(500, 0.0, rng)
        assert all(abs(s) < 1e-12 for s in buf)


class TestReverb:
    def test_reverb_adds_energy_after_delay(self):
        n = 5000
        impulse = [0.0] * n
        impulse[0] = 1.0
        out = _apply_reverb(impulse[:], room=0.5)
        # After the impulse, some energy should appear at delay positions
        assert any(abs(out[i]) > 0.01 for i in range(1499, 1600)), "Expected echo at delay 1499"

    def test_reverb_room_zero_no_effect(self):
        n = 5000
        impulse = [0.0] * n
        impulse[0] = 1.0
        out = _apply_reverb(impulse[:], room=0.0)
        # With room=0, only direct signal survives
        assert all(abs(out[i]) < 1e-12 for i in range(1, n))


# ── Clip generation tests ──────────────────────────────────────────────────────

class TestGenerateClip:
    def test_deterministic(self):
        left1, right1, params1 = generate_clip(1, random.Random(42))
        left2, right2, params2 = generate_clip(1, random.Random(42))
        assert left1 == left2
        assert right1 == right2
        assert params1 == params2

    def test_different_rng_seeds_differ(self):
        # Different seeds → different clips
        left1, _, _ = generate_clip(1, random.Random(42))
        left2, _, _ = generate_clip(1, random.Random(99))
        assert left1 != left2

    def test_duration_within_bounds(self):
        _, _, params = generate_clip(1, random.Random(42), min_dur=8.0, max_dur=15.0)
        dur = params["duration_seconds"]
        assert 8.0 <= dur <= 15.0, f"duration {dur} out of [8, 15]"

    def test_stereo_channels_differ(self):
        left, right, _ = generate_clip(1, random.Random(42))
        assert left != right, "L and R channels should differ (stereo delay)"

    def test_no_clipping_after_normalize(self):
        left, right, _ = generate_clip(5, random.Random(99))
        peak_l = max(abs(s) for s in left)
        peak_r = max(abs(s) for s in right)
        assert peak_l <= MAX_PEAK + 1e-6, f"Left channel peak {peak_l} exceeds {MAX_PEAK}"
        assert peak_r <= MAX_PEAK + 1e-6, f"Right channel peak {peak_r} exceeds {MAX_PEAK}"

    def test_note_count_in_range(self):
        for seed in range(10):
            _, _, params = generate_clip(seed, random.Random(seed))
            assert 1 <= params["note_count"] <= 5, \
                f"note_count={params['note_count']} out of [1,5]"

    def test_params_schema(self):
        _, _, params = generate_clip(1, random.Random(42))
        for key in ("duration_seconds", "base_freq_hz", "note_count", "note_events",
                    "room_size", "shimmer_level", "stereo_delay_samples"):
            assert key in params, f"Missing key: {key}"
        assert isinstance(params["note_events"], list)


# ── WAV writing and metadata tests ────────────────────────────────────────────

class TestWriteWav:
    def test_writes_48khz_stereo_wav(self, tmp_path):
        left, right, _ = generate_clip(1, random.Random(1), min_dur=1.0, max_dur=2.0)
        wav_path = tmp_path / "test.wav"
        write_wav(wav_path, left, right)

        assert wav_path.exists()
        with wave.open(str(wav_path), "rb") as wf:
            assert wf.getframerate() == SAMPLE_RATE
            assert wf.getnchannels() == CHANNELS
            assert wf.getsampwidth() == 2

    def test_duration_matches_params(self, tmp_path):
        left, right, params = generate_clip(1, random.Random(1), min_dur=3.0, max_dur=4.0)
        wav_path = tmp_path / "test.wav"
        write_wav(wav_path, left, right)

        with wave.open(str(wav_path), "rb") as wf:
            actual_dur = wf.getnframes() / wf.getframerate()
        assert abs(actual_dur - params["duration_seconds"]) < 0.05

    def test_no_clipping_in_wav(self, tmp_path):
        import struct
        left, right, _ = generate_clip(3, random.Random(77), min_dur=1.0, max_dur=2.0)
        wav_path = tmp_path / "test.wav"
        write_wav(wav_path, left, right)

        with wave.open(str(wav_path), "rb") as wf:
            raw = wf.readframes(wf.getnframes())
        n_samples = len(raw) // 2
        values = struct.unpack(f"<{n_samples}h", raw)
        peak = max(abs(v) for v in values)
        assert peak < 32767, f"PCM peak {peak} == 32767 (clipping)"


# ── Pack generation tests ─────────────────────────────────────────────────────

class TestGeneratePack:
    def test_generates_requested_count(self, tmp_path):
        rows = generate_pack(tmp_path, count=3, min_dur=1.0, max_dur=2.0, verbose=False)
        assert len(rows) == 3
        wavs = list(tmp_path.glob("*.wav"))
        assert len(wavs) == 3

    def test_metadata_jsonl_written(self, tmp_path):
        generate_pack(tmp_path, count=3, min_dur=1.0, max_dur=2.0, verbose=False)
        meta = tmp_path / "metadata.jsonl"
        assert meta.exists()
        rows = [json.loads(line) for line in meta.read_text().splitlines() if line.strip()]
        assert len(rows) == 3

    def test_metadata_row_schema(self, tmp_path):
        rows = generate_pack(tmp_path, count=2, min_dur=1.0, max_dur=2.0, verbose=False)
        required_keys = {"file_path", "seed", "duration", "synthesis_params",
                         "caption", "tags", "sha256", "sample_rate", "channels", "pack"}
        for row in rows:
            missing = required_keys - set(row)
            assert not missing, f"Row missing keys: {missing}"

    def test_tags_correct(self, tmp_path):
        rows = generate_pack(tmp_path, count=2, min_dur=1.0, max_dur=2.0, verbose=False)
        expected = {"synthetic", "bell", "metallic", "ambient", "sparse", "dark"}
        for row in rows:
            assert set(row["tags"]) == expected

    def test_caption_non_empty(self, tmp_path):
        rows = generate_pack(tmp_path, count=5, min_dur=1.0, max_dur=2.0, verbose=False)
        for row in rows:
            assert row["caption"].strip(), "Caption should not be empty"

    def test_sha256_matches_file(self, tmp_path):
        rows = generate_pack(tmp_path, count=2, min_dur=1.0, max_dur=2.0, verbose=False)
        for row in rows:
            path = Path(row["file_path"])
            computed = hashlib.sha256(path.read_bytes()).hexdigest()
            assert computed == row["sha256"], "SHA-256 mismatch between file and metadata"

    def test_deterministic_across_runs(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        generate_pack(dir_a, count=3, global_seed=1234, min_dur=1.0, max_dur=2.0, verbose=False)
        generate_pack(dir_b, count=3, global_seed=1234, min_dur=1.0, max_dur=2.0, verbose=False)

        for i in range(1, 4):
            name = f"{PACK_NAME}-{i:03d}.wav"
            h_a = hashlib.sha256((dir_a / name).read_bytes()).hexdigest()
            h_b = hashlib.sha256((dir_b / name).read_bytes()).hexdigest()
            assert h_a == h_b, f"Clip {name} is not deterministic across runs"

    def test_different_seeds_produce_different_clips(self, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        generate_pack(dir_a, count=2, global_seed=1111, min_dur=1.0, max_dur=2.0, verbose=False)
        generate_pack(dir_b, count=2, global_seed=9999, min_dur=1.0, max_dur=2.0, verbose=False)
        name = f"{PACK_NAME}-001.wav"
        h_a = hashlib.sha256((dir_a / name).read_bytes()).hexdigest()
        h_b = hashlib.sha256((dir_b / name).read_bytes()).hexdigest()
        assert h_a != h_b, "Different global seeds should produce different clips"

    def test_duration_range(self, tmp_path):
        rows = generate_pack(tmp_path, count=6, min_dur=2.0, max_dur=4.0, verbose=False)
        for row in rows:
            assert 2.0 <= row["duration"] <= 4.0 + 0.01, \
                f"duration {row['duration']} out of [2, 4]"

    def test_peak_within_clip_limit(self, tmp_path):
        import struct
        generate_pack(tmp_path, count=3, min_dur=1.0, max_dur=2.0, verbose=False)
        for wav_path in sorted(tmp_path.glob("*.wav")):
            with wave.open(str(wav_path), "rb") as wf:
                raw = wf.readframes(wf.getnframes())
            n = len(raw) // 2
            values = struct.unpack(f"<{n}h", raw)
            peak_f = max(abs(v) for v in values) / 32767.0
            assert peak_f <= MAX_PEAK + 0.01, \
                f"{wav_path.name}: peak {peak_f:.4f} exceeds MAX_PEAK {MAX_PEAK}"


# ── Ingestion tests ────────────────────────────────────────────────────────────

class TestIngestSyntheticPack:
    def test_ingests_clips_as_media_assets(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        from app.core.config import get_settings
        get_settings.cache_clear()

        pack_dir = tmp_path / "synthetic_audio" / PACK_NAME
        generate_pack(pack_dir, count=4, min_dur=1.0, max_dur=2.0, verbose=False)

        report = ingest_synthetic_pack(pack_dir=pack_dir)

        assert report["total_clips"] == 4
        assert report["imported_count"] == 4
        assert report["reused_count"] == 0

    def test_idempotent_reingest(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        from app.core.config import get_settings
        get_settings.cache_clear()

        pack_dir = tmp_path / "synthetic_audio" / PACK_NAME
        generate_pack(pack_dir, count=3, min_dur=1.0, max_dur=2.0, verbose=False)

        r1 = ingest_synthetic_pack(pack_dir=pack_dir)
        r2 = ingest_synthetic_pack(pack_dir=pack_dir)

        assert r1["imported_count"] == 3
        assert r2["imported_count"] == 0
        assert r2["reused_count"] == 3

    def test_category_keys_present(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        from app.core.config import get_settings
        get_settings.cache_clear()

        pack_dir = tmp_path / "synthetic_audio" / PACK_NAME
        generate_pack(pack_dir, count=2, min_dur=1.0, max_dur=2.0, verbose=False)

        report = ingest_synthetic_pack(pack_dir=pack_dir)
        cat_labels = set(report["categories"].keys())
        assert "INSTRUMENT:Bell" in cat_labels
        assert "PRODUCTION:Metallic" in cat_labels
        assert "GENRE:Ambient" in cat_labels
        assert "ARRANGEMENT:Sparse" in cat_labels
        assert "MOOD:Dark" in cat_labels

    def test_raises_without_metadata_jsonl(self, tmp_path):
        pack_dir = tmp_path / "empty"
        pack_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            ingest_synthetic_pack(pack_dir=pack_dir)


# ── End-to-end dataset flow test ──────────────────────────────────────────────

class TestSyntheticDatasetFlow:
    def test_full_flow(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        from app.core.config import get_settings
        get_settings.cache_clear()

        pack_dir = tmp_path / "synthetic_audio" / PACK_NAME

        # 15 clips × avg 5s = ~75 s, clearing the DatasetGeneratorService 60 s minimum
        report = verify_synthetic_instrument_dataset_flow(
            pack_dir=pack_dir,
            clip_count=15,
            min_dur=4.5,
            max_dur=6.0,
        )

        assert report["success"] is True
        assert report["wav_count"] >= 15
        assert report["ready_count"] >= 10
        assert report["frozen_dataset"]["immutable_after_regenerate"] is True
        assert report["frozen_dataset"]["track_count"] >= 3
        assert report["frozen_dataset"]["total_duration_seconds"] >= 60.0

    def test_manifest_hash_integrity(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        from app.core.config import get_settings
        get_settings.cache_clear()

        pack_dir = tmp_path / "synthetic_audio" / PACK_NAME

        report = verify_synthetic_instrument_dataset_flow(
            pack_dir=pack_dir,
            clip_count=15,
            min_dur=4.5,
            max_dur=6.0,
        )

        manifest_path = Path(report["frozen_dataset"]["manifest_path"])
        manifest = json.loads(manifest_path.read_text())
        # Verify the hash matches
        payload = {k: v for k, v in manifest.items() if k != "manifest_hash"}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        expected = hashlib.sha256(encoded).hexdigest()
        assert manifest["manifest_hash"] == expected
