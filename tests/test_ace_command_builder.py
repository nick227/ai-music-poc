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


def test_ace_command_builder_passes_lora_path_and_scale(tmp_path):
    settings = Settings(
        DATA_DIR=tmp_path,
        ACE_COMMAND_TEMPLATE='$python $script --lora-path $lora_path --lora-scale $lora_scale --use-lora $use_lora --output $output_path',
        ACE_PYTHON=Path('python'),
        ACE_SCRIPT=Path('infer.py'),
    )
    lora = str(tmp_path / 'lora' / 'final')
    req = GenerationRequest(
        prompt='styled dark disco',
        duration_seconds=10,
        lora_path=lora,
        lora_scale=0.8,
    )
    output = tmp_path / 'outputs' / 'styled.wav'
    cmd = AceCommandBuilder(settings).build(req, output)
    assert '--lora-path' in cmd
    assert lora in cmd
    assert '0.8' in cmd
    assert 'true' in cmd


def test_ace_command_builder_sets_use_lora_false_without_lora_path(tmp_path):
    settings = Settings(
        DATA_DIR=tmp_path,
        ACE_COMMAND_TEMPLATE='$python $script --use-lora $use_lora --lora-path $lora_path --output $output_path',
        ACE_PYTHON=Path('python'),
        ACE_SCRIPT=Path('infer.py'),
    )
    req = GenerationRequest(prompt='base model generation', duration_seconds=10)
    output = tmp_path / 'outputs' / 'base.wav'
    cmd = AceCommandBuilder(settings).build(req, output)
    lora_idx = cmd.index('--lora-path')
    use_lora_idx = cmd.index('--use-lora')
    assert cmd[use_lora_idx + 1] == 'false'
    assert cmd[lora_idx + 1] == '__none__'
