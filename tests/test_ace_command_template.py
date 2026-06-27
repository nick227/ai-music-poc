"""
ACE_COMMAND_TEMPLATE rendering tests.
Verifies token substitution, optional-field handling, and template validation.
"""
from pathlib import Path

import pytest

from app.core.command_template import render_command, validate_template
from app.core.config import Settings
from app.domain.models import GenerationRequest
from app.generators.ace_step.command_builder import AceCommandBuilder


FULL_TEMPLATE = (
    "$python $script"
    " --prompt-file $prompt_file"
    " --lyrics-file $lyrics_file"
    " --output $output_path"
    " --duration $duration_seconds"
    " --seed $seed"
    " --bpm $bpm"
    " --key $key"
    " --mode $mode"
    " --structure $structure"
    " --quality $quality"
    " --device $device"
    " --model-dir $model_dir"
    " --guidance $guidance_scale"
)


def _builder(tmp_path: Path, template: str = FULL_TEMPLATE) -> AceCommandBuilder:
    return AceCommandBuilder(Settings(
        DATA_DIR=tmp_path,
        ACE_COMMAND_TEMPLATE=template,
        ACE_PYTHON=Path("python"),
        ACE_SCRIPT=Path("infer.py"),
        ACE_MODEL_DIR=tmp_path / "models",
        ACE_DEVICE="cpu",
    ))


def _req(**overrides) -> GenerationRequest:
    data = {
        "prompt": "dark electro",
        "lyrics": "verse one",
        "duration_seconds": 10,
    }
    data.update(overrides)
    return GenerationRequest.model_validate(data)


# ---------------------------------------------------------------------------
# validate_template
# ---------------------------------------------------------------------------

def test_validate_template_passes_with_required_tokens():
    warnings = validate_template("$python $script --output $output_path --prompt-file $prompt_file")
    assert warnings == []


def test_validate_template_warns_when_output_path_missing():
    warnings = validate_template("$python $script --prompt-file $prompt_file")
    assert any("output_path" in w for w in warnings)


def test_validate_template_warns_when_prompt_token_missing():
    warnings = validate_template("$python $script --output $output_path")
    assert any("prompt" in w for w in warnings)


def test_validate_template_warns_for_empty_template():
    warnings = validate_template("")
    assert any("empty" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# render_command token substitution
# ---------------------------------------------------------------------------

def test_render_command_substitutes_all_tokens():
    template = "$python $script --output $output_path --prompt-file $prompt_file"
    rendered = render_command(template, {
        "python": "python3",
        "script": "infer.py",
        "output_path": "/tmp/out.wav",
        "prompt_file": "/tmp/prompt.txt",
    })
    assert rendered == ["python3", "infer.py", "--output", "/tmp/out.wav", "--prompt-file", "/tmp/prompt.txt"]


def test_render_command_leaves_unknown_tokens_intact():
    """safe_substitute: unknown tokens pass through as literal text, never raise."""
    rendered = render_command("$python $unknown_token --output $output_path", {
        "python": "python3",
        "output_path": "/tmp/out.wav",
    })
    assert "$unknown_token" in rendered


# ---------------------------------------------------------------------------
# AceCommandBuilder: optional fields render as empty strings
# ---------------------------------------------------------------------------

def test_command_builder_seed_set_appears_in_command(tmp_path):
    """When seed is provided it must appear as a token in the rendered command."""
    builder = _builder(tmp_path)
    req = _req(seed=42)
    output = tmp_path / "out.wav"
    cmd = builder.build(req, output)
    assert "42" in cmd


def test_command_builder_seed_none_no_numeric_value_after_flag(tmp_path):
    """seed=None serialises to empty string; shlex.split drops it from the token list.

    The practical consequence: --seed is followed immediately by the next flag.
    This documents current behaviour so regressions are caught.  Runner scripts
    must handle a missing seed value gracefully.
    """
    builder = _builder(tmp_path)
    req = _req(seed=None)
    output = tmp_path / "out.wav"
    cmd = builder.build(req, output)
    if "--seed" in cmd:
        seed_idx = cmd.index("--seed")
        # The token right after --seed must NOT be a plain integer (seed was dropped)
        next_token = cmd[seed_idx + 1] if seed_idx + 1 < len(cmd) else ""
        assert not next_token.lstrip("-").isdigit(), (
            f"seed=None should not produce a numeric value, got {next_token!r}"
        )


def test_command_builder_bpm_set_appears_in_command(tmp_path):
    """When bpm is provided it must appear as a token in the rendered command."""
    builder = _builder(tmp_path)
    req = _req(bpm=120)
    output = tmp_path / "out.wav"
    cmd = builder.build(req, output)
    assert "120" in cmd


def test_command_builder_key_set_appears_in_command(tmp_path):
    """When key is provided it must appear as a token in the rendered command."""
    builder = AceCommandBuilder(Settings(
        DATA_DIR=tmp_path,
        ACE_COMMAND_TEMPLATE="$python $script --key $key --output $output_path --prompt-file $prompt_file",
        ACE_PYTHON=Path("python"),
        ACE_SCRIPT=Path("infer.py"),
    ))
    req = _req(key="C#")
    output = tmp_path / "out.wav"
    cmd = builder.build(req, output)
    assert "C#" in cmd


def test_command_builder_output_path_in_command(tmp_path):
    builder = _builder(tmp_path)
    req = _req()
    output = tmp_path / "outputs" / "song.wav"
    cmd = builder.build(req, output)
    assert str(output) in cmd


def test_command_builder_writes_temp_files(tmp_path):
    builder = _builder(tmp_path)
    req = _req(lyrics="verse one\nchorus here", seed=77)
    output = tmp_path / "song.wav"
    builder.build(req, output)
    stem = output.stem  # "song"
    assert (tmp_path / "tmp" / stem / "lyrics.txt").read_text() == "verse one\nchorus here"
    assert (tmp_path / "tmp" / stem / "prompt.txt").read_text().startswith("dark electro")


def test_command_builder_genre_mood_tags_joined(tmp_path):
    builder = AceCommandBuilder(Settings(
        DATA_DIR=tmp_path,
        ACE_COMMAND_TEMPLATE="$python $script --genres $genre_tags --moods $mood_tags --output $output_path --prompt-file $prompt_file",
        ACE_PYTHON=Path("python"),
        ACE_SCRIPT=Path("infer.py"),
    ))
    req = _req(genre_tags=["disco", "funk"], mood_tags=["happy", "groovy"])
    cmd = builder.build(req, tmp_path / "out.wav")
    genres_idx = cmd.index("--genres")
    assert cmd[genres_idx + 1] == "disco,funk"
    moods_idx = cmd.index("--moods")
    assert cmd[moods_idx + 1] == "happy,groovy"


def test_command_builder_voice_direction_in_prompt_file(tmp_path):
    builder = _builder(tmp_path)
    req = _req(singing_voice="male", vocal_style="warm baritone", vocal_intensity=0.8)
    output = tmp_path / "vd.wav"
    builder.build(req, output)
    prompt_text = (tmp_path / "tmp" / "vd" / "prompt.txt").read_text()
    assert "male singing voice" in prompt_text
    assert "warm baritone" in prompt_text
    assert "0.80" in prompt_text


def test_command_builder_no_voice_direction_when_auto(tmp_path):
    builder = _builder(tmp_path)
    req = _req(singing_voice="auto", vocal_style=None)
    output = tmp_path / "auto.wav"
    builder.build(req, output)
    prompt_text = (tmp_path / "tmp" / "auto" / "prompt.txt").read_text()
    assert "Vocal direction" not in prompt_text
