import pytest
from pathlib import Path
from app.domain.models import GenerationRequest
from app.generators.procedural import ProceduralGenerator

def _request(seed: int) -> GenerationRequest:
    return GenerationRequest.model_validate({
        "title": "Portamento Test",
        "prompt": "pop hook",
        "lyrics": "testing pitch glide",
        "duration_seconds": 10,
        "mode": "song",
        "structure": "verse_chorus",
        "quality": "draft",
        "seed": seed,
    })

def test_procedural_lead_portamento_continuity(tmp_path: Path):
    """Ensure the procedural generator runs without crashing with the new portamento logic."""
    generator = ProceduralGenerator()
    out_path = tmp_path / "portamento.wav"
    result = generator.generate(_request(42), out_path)
    
    assert out_path.exists()
    assert out_path.stat().st_size > 1000
    assert result.duration_seconds == 10

def test_procedural_lead_portamento_deterministic(tmp_path: Path):
    """Ensure that the procedural generator is still fully deterministic."""
    generator = ProceduralGenerator()
    out1 = tmp_path / "out1.wav"
    out2 = tmp_path / "out2.wav"
    
    generator.generate(_request(101), out1)
    generator.generate(_request(101), out2)
    
    # Files should be exactly identical
    assert out1.read_bytes() == out2.read_bytes()
