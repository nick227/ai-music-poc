from pathlib import Path

from app.core.config import Settings
from app.generators.ace_step.health import get_ace_status, run_ace_python_diagnostic


def test_ace_status_requires_valid_template(tmp_path):
    script = tmp_path / 'runner.py'
    script.write_text('print("ok")')
    model_dir = tmp_path / 'models'
    model_dir.mkdir()
    settings = Settings(
        DATA_DIR=tmp_path,
        ACE_ENABLED=True,
        ACE_PYTHON=Path('python'),
        ACE_SCRIPT=script,
        ACE_MODEL_DIR=model_dir,
        ACE_COMMAND_TEMPLATE='$python $script --prompt-file $prompt_file',
    )
    status = get_ace_status(settings)
    assert status.command_template_valid is False
    assert status.can_generate is False
    assert any('output_path' in warning for warning in status.warnings)


def test_python_diagnostic_runs_with_default_python(tmp_path):
    settings = Settings(DATA_DIR=tmp_path, ACE_PYTHON=Path('python'))
    diagnostic = run_ace_python_diagnostic(settings)
    assert 'command' in diagnostic
    assert 'ok' in diagnostic


def test_model_status_test_endpoint(client):
    c, _ = client
    res = c.post('/api/model-status/test')
    assert res.status_code == 200
    body = res.json()
    assert 'diagnostic' in body
    assert 'packages' in body
    assert 'dry_run' in body
    assert 'recommended_actions' in body
    assert 'status' in body
