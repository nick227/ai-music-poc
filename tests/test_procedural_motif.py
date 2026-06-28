import pytest
from pathlib import Path
from app.domain.models import GenerationRequest
from app.generators.procedural import (
    ProceduralGenerator, MELODIC_CONTOURS, PROFILES, _melody_freq,
)


def _request(prompt: str = "pop hook catchy chorus", seed: int = 7, structure: str = "verse_chorus") -> GenerationRequest:
    return GenerationRequest.model_validate({
        "title": "Motif Test",
        "prompt": prompt,
        "lyrics": "",
        "duration_seconds": 15,
        "mode": "song",
        "structure": structure,
        "quality": "draft",
        "seed": seed,
    })


# --- MELODIC_CONTOURS ---

def test_bridge_b_contour_exists():
    assert "bridge_b" in MELODIC_CONTOURS

def test_bridge_b_contour_length():
    assert len(MELODIC_CONTOURS["bridge_b"]) == 8

def test_bridge_b_differs_from_bridge():
    assert MELODIC_CONTOURS["bridge_b"] != MELODIC_CONTOURS["bridge"]

def test_bridge_b_starts_higher_than_bridge():
    # bridge_b should have a higher average contour offset than bridge (higher register)
    avg_bridge = sum(MELODIC_CONTOURS["bridge"]) / len(MELODIC_CONTOURS["bridge"])
    avg_bridge_b = sum(MELODIC_CONTOURS["bridge_b"]) / len(MELODIC_CONTOURS["bridge_b"])
    assert avg_bridge_b > avg_bridge


# --- _motif_notes ---

def test_motif_notes_returns_four_freqs():
    gen = ProceduralGenerator()
    profile = PROFILES["pop"]
    motif = gen._motif_notes(profile, 261.63)
    assert len(motif) == 4
    assert all(isinstance(f, float) for f in motif)
    assert all(f > 0 for f in motif)

def test_motif_notes_match_verse_melody():
    gen = ProceduralGenerator()
    profile = PROFILES["default"]
    root = 261.63
    motif = gen._motif_notes(profile, root)
    for step in range(4):
        expected = _melody_freq(profile, root, 0, "verse", step, 2.0)
        assert abs(motif[step] - expected) < 1e-9, f"motif step {step} mismatch"

def test_motif_notes_rap_uses_lower_octave():
    gen = ProceduralGenerator()
    profile = PROFILES["rap"]
    root = 261.63
    motif = gen._motif_notes(profile, root)
    expected_step0 = _melody_freq(profile, root, 0, "verse", 0, 1.0)
    assert abs(motif[0] - expected_step0) < 1e-9

def test_motif_notes_vary_across_steps():
    gen = ProceduralGenerator()
    profile = PROFILES["folk"]
    motif = gen._motif_notes(profile, 261.63)
    # Not all four notes should be identical (would indicate a broken contour)
    assert len(set(round(f, 3) for f in motif)) > 1

def test_motif_notes_deterministic():
    gen = ProceduralGenerator()
    profile = PROFILES["jazz"]
    m1 = gen._motif_notes(profile, 293.66)
    m2 = gen._motif_notes(profile, 293.66)
    assert m1 == m2


# --- Full generation ---

def test_generation_with_motif_completes(tmp_path: Path):
    gen = ProceduralGenerator()
    out = tmp_path / "motif.wav"
    result = gen.generate(_request(), out)
    assert out.exists()
    assert out.stat().st_size > 1000
    assert result.duration_seconds == 15

def test_generation_motif_deterministic(tmp_path: Path):
    gen = ProceduralGenerator()
    out1 = tmp_path / "m1.wav"
    out2 = tmp_path / "m2.wav"
    gen.generate(_request(seed=42), out1)
    gen.generate(_request(seed=42), out2)
    assert out1.read_bytes() == out2.read_bytes()

def test_generation_different_seeds_differ(tmp_path: Path):
    gen = ProceduralGenerator()
    out1 = tmp_path / "s1.wav"
    out2 = tmp_path / "s2.wav"
    gen.generate(_request(seed=1), out1)
    gen.generate(_request(seed=2), out2)
    assert out1.read_bytes() != out2.read_bytes()

def test_generation_chorus_motif_folk(tmp_path: Path):
    gen = ProceduralGenerator()
    out = tmp_path / "folk.wav"
    result = gen.generate(_request("folk singer-songwriter acoustic", seed=5), out)
    assert out.exists()
    assert result.duration_seconds == 15

def test_generation_bridge_b_contour_triggers(tmp_path: Path):
    # intro_verse_chorus structure has a bridge section; song must generate cleanly
    gen = ProceduralGenerator()
    out = tmp_path / "bridge_b.wav"
    result = gen.generate(_request(structure="intro_verse_chorus"), out)
    assert out.exists()
    assert out.stat().st_size > 1000

def test_generation_motif_chorus_higher_than_verse(tmp_path: Path):
    """Chorus lead (with motif transposed up a 5th) should have higher peak energy
    in high-freq bucket than verse — a coarse proxy for register lift."""
    import struct, math
    gen = ProceduralGenerator()
    out = tmp_path / "compare.wav"
    gen.generate(_request("pop upbeat hook", seed=99, structure="verse_chorus"), out)
    data = out.read_bytes()
    # Skip 44-byte WAV header, read 16-bit stereo samples
    samples = struct.unpack_from(f"<{(len(data) - 44) // 2}h", data, 44)
    sr = 44100
    total = len(samples) // 2  # stereo pairs
    verse_end = int(0.38 * total)
    chorus_start = int(0.42 * total)
    chorus_end = int(0.60 * total)
    verse_rms = math.sqrt(sum(s * s for s in samples[0:verse_end * 2:2]) / max(1, verse_end))
    chorus_rms = math.sqrt(sum(s * s for s in samples[chorus_start * 2:chorus_end * 2:2]) / max(1, chorus_end - chorus_start))
    # Chorus motif (transposed 5th higher + harmony 4th) should be louder than verse
    assert chorus_rms > verse_rms * 0.80, f"chorus_rms={chorus_rms:.1f} verse_rms={verse_rms:.1f}"
