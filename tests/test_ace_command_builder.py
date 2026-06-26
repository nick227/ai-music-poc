from pathlib import Path

from app.core.config import Settings
from app.generators.ace_step.command_builder import AceCommandBuilder
from app.domain.models import GenerationRequest


def test_ace_command_builder_renders_files(tmp_path):
    settings = Settings(
        DATA_DIR=tmp_path,
        ACE_COMMAND_TEMPLATE='$python $script --prompt-file $prompt_file --lyrics-file $lyrics_file --output $output_path --duration $duration_seconds',
        ACE_PYTHON=Path('python'),
        ACE_SCRIPT=Path('infer.py'),
    )
    req = GenerationRequest(prompt='dark disco', lyrics='hello world', duration_seconds=10)
    output = tmp_path / 'outputs' / 'x.wav'
    cmd = AceCommandBuilder(settings).build(req, output)
    assert '--prompt-file' in cmd
    assert str(output) in cmd
    assert (tmp_path / 'tmp' / 'x' / 'lyrics.txt').read_text() == 'hello world'


def test_ace_command_builder_writes_voice_direction(tmp_path):
    settings = Settings(
        DATA_DIR=tmp_path,
        ACE_COMMAND_TEMPLATE='$python $script --voice $singing_voice --intensity $vocal_intensity --prompt-file $prompt_file --output $output_path',
        ACE_PYTHON=Path('python'),
        ACE_SCRIPT=Path('infer.py'),
    )
    req = GenerationRequest(
        prompt='dark disco',
        lyrics='hello world',
        duration_seconds=10,
        singing_voice='male',
        vocal_style='dry close mic',
        vocal_intensity=0.75,
    )
    output = tmp_path / 'outputs' / 'voice.wav'
    cmd = AceCommandBuilder(settings).build(req, output)
    prompt_text = (tmp_path / 'tmp' / 'voice' / 'prompt.txt').read_text()
    assert '--voice' in cmd
    assert 'male' in cmd
    assert '0.75' in cmd
    assert 'Vocal direction: male singing voice, dry close mic.' in prompt_text
