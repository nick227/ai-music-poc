from pathlib import Path

from app.domain.models import GenerationRequest
from app.generators.procedural import ProceduralGenerator
from app.generators.vocal_plan import load_vocal_plan
from app.generators.vocal_engine import resolve_voice


def _request(prompt: str, **overrides) -> GenerationRequest:
    data = {
        "title": "Style Test",
        "prompt": prompt,
        "lyrics": "one two three four",
        "duration_seconds": 10,
        "mode": "song",
        "structure": "verse_chorus",
        "quality": "draft",
        "seed": 7,
    }
    data.update(overrides)
    return GenerationRequest.model_validate(data)


def test_procedural_v34_reports_style_profiles(tmp_path: Path):
    generator = ProceduralGenerator()
    cases = [
        ("dark disco club song", "club"),
        ("heavy rap mixtape with 808", "rap"),
        ("ambient instrumental long pads", "ambient"),
        ("indie acoustic fx guitar", "acoustic"),
        ("lo-fi dusty tape wobble loop", "lofi"),
    ]
    for index, (prompt, expected) in enumerate(cases):
        result = generator.generate(_request(prompt), tmp_path / f"{index}.wav")
        assert result.metadata["engine"].startswith("procedural-v3.")
        assert result.metadata["style_profile"] == expected
        assert result.metadata["lyrics_behavior"] in ("synthetic_singing_voice", "formant_singing")
        assert result.metadata["singing_voice"] in {"female", "male", "choir", "robot", "whisper"}


def test_phase2_preset_profile_routing(tmp_path: Path):
    """Phase 2 style packs must resolve to the intended profile — not ambient/default."""
    generator = ProceduralGenerator()
    cases = [
        # (prompt_snippet, expected_profile, mode)
        ("dark cinematic piano, minor key, close felt piano, low pulses", "cinematic", "song"),
        ("French disco, glossy drums, analog bass, bittersweet vocal", "disco", "song"),
        ("heavy rap mixtape, hard drums, low 808, ominous sample, confident hook", "rap", "song"),
        ("ambient post-indie, hazy guitars, soft drums, washed synth pads", "acoustic", "song"),
        ("retro electro, analog arpeggios, punchy drum machine, neon bass", "club", "song"),
        ("cinematic trailer cue, rising tension, low pulses, dramatic hit", "cinematic", "instrumental"),
    ]
    for index, (prompt, expected, mode) in enumerate(cases):
        result = generator.generate(_request(prompt, mode=mode), tmp_path / f"p2_{index}.wav")
        assert result.metadata["style_profile"] == expected, (
            f"Expected '{expected}' for prompt '{prompt}' but got '{result.metadata['style_profile']}'"
        )


def test_negative_prompt_does_not_select_style(tmp_path: Path):
    generator = ProceduralGenerator()
    result = generator.generate(
        _request("dark electronic song", negative_prompt="no acoustic guitar, no lofi"),
        tmp_path / "negative.wav",
    )
    assert result.metadata["style_profile"] not in {"acoustic", "lofi"}


def test_ambient_profile_disables_drums(tmp_path: Path):
    generator = ProceduralGenerator()
    result = generator.generate(_request("ambient instrumental long pads", mode="instrumental"), tmp_path / "ambient.wav")
    assert result.metadata["style_profile"] == "ambient"
    assert result.metadata["drums_enabled"] is False


def test_requested_singing_voice_is_reported(tmp_path: Path):
    generator = ProceduralGenerator()
    result = generator.generate(
        _request("bright pop hook", singing_voice="choir", vocal_intensity=0.8),
        tmp_path / "choir.wav",
    )
    assert result.metadata["lyrics_behavior"] in ("synthetic_singing_voice", "formant_singing")
    assert result.metadata["singing_voice"] == "choir"
    assert result.metadata["vocal_intensity"] == 0.8


def test_high_quality_exports_vocal_stem(tmp_path: Path):
    generator = ProceduralGenerator()
    lyrics = """I saw your shadow in the blue light
Dancing where the city ends"""
    result = generator.generate(
        _request("pop hook", lyrics=lyrics, quality="high", duration_seconds=12),
        tmp_path / "song.wav",
    )
    assert result.metadata["vocal_stem_file"] == "song_vocal.wav"
    assert (tmp_path / "song_vocal.wav").exists()
    assert result.metadata["syllable_events"] >= 2
    assert result.metadata["vocal_plan_file"] == "song_vocal_plan.json"
    assert (tmp_path / "song_vocal_plan.json").exists()
    plan = load_vocal_plan(tmp_path / "song_vocal_plan.json")
    assert plan.syllable_count() >= 2


def test_line_aware_lyric_timeline():
    from app.generators.vocal_plan import build_vocal_plan, syllable_at

    lyrics = "hello world\nfoo bar"
    plan = build_vocal_plan(
        lyrics,
        bpm=120,
        key=None,
        duration_beats=32.0,
        scale=[0, 2, 4, 5, 7, 9, 11],
        root_hz=261.63,
    )
    assert plan.syllable_count() >= 4
    foo = next(s for s in plan.flat_syllables() if s.text.startswith("f"))
    hit = syllable_at(plan, foo.beat_start + 0.01)
    assert hit is not None
    assert hit[0].text.startswith("f")


def test_auto_voice_detects_male_from_prompt():
    request = _request("emotional male vocal ballad")
    assert resolve_voice(request, request.prompt.lower()).name == "male"
