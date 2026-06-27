from pathlib import Path
import importlib.util


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ace_smoke_test.py"
SPEC = importlib.util.spec_from_file_location("ace_smoke_test", MODULE_PATH)
assert SPEC and SPEC.loader
ace_smoke_test = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ace_smoke_test)


def test_resolve_output_path_defaults_to_temp():
    assert ace_smoke_test.resolve_output_path(None, False) is None


def test_resolve_output_path_keep_output_uses_model_outputs():
    assert ace_smoke_test.resolve_output_path(None, True) == ace_smoke_test.DEFAULT_KEPT_OUTPUT


def test_resolve_output_path_resolves_relative_output():
    assert ace_smoke_test.resolve_output_path("data/model_outputs/custom.wav", False) == (
        ace_smoke_test.ROOT / "data" / "model_outputs" / "custom.wav"
    )


def test_resolve_output_path_keeps_absolute_output(tmp_path):
    output = tmp_path / "custom.wav"
    assert ace_smoke_test.resolve_output_path(str(output), False) == output
