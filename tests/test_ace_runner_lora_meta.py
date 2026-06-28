from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "ace_runner.py"


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("ace_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_lora_meta_from_hook():
    runner = _load_runner_module()
    meta = runner.build_lora_meta(
        use_lora=True,
        lora_path=Path("/tmp/final"),
        lora_scale=0.75,
        hook_meta={
            "loraLoadAttempted": True,
            "loraLoadSucceeded": True,
            "loraLoadMessage": "loaded",
            "loraPath": "/tmp/final",
            "loraScale": 0.75,
        },
    )
    assert meta["loraLoadSucceeded"] is True
    assert meta["loraScale"] == 0.75


def test_write_and_emit_lora_meta_sidecar(tmp_path):
    runner = _load_runner_module()
    output = tmp_path / "out.wav"
    payload = runner.build_lora_meta(use_lora=False, lora_path=None, lora_scale=1.0)
    path = runner.write_ace_meta_sidecar(output, payload)
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8"))["loraLoadAttempted"] is False


def test_prepare_peft_lora_dir_accepts_studio_lora_names(tmp_path):
    runner = _load_runner_module()
    lora_dir = tmp_path / "lora"
    scratch = tmp_path / "scratch"
    lora_dir.mkdir()
    (lora_dir / "lora_config.json").write_text("{}", encoding="utf-8")
    (lora_dir / "lora.safetensors").write_bytes(b"weights")

    peft_dir, missing = runner.prepare_peft_lora_dir(lora_dir, scratch)

    assert missing == []
    assert peft_dir is not None
    assert (peft_dir / "adapter_config.json").is_file()
    assert (peft_dir / "adapter_model.safetensors").is_file()


def test_prepare_peft_lora_dir_reports_missing_lora_files(tmp_path):
    runner = _load_runner_module()
    lora_dir = tmp_path / "lora"
    lora_dir.mkdir()

    peft_dir, missing = runner.prepare_peft_lora_dir(lora_dir, tmp_path / "scratch")

    assert peft_dir is None
    assert set(missing) == {"lora_config.json", "lora.safetensors"}


def test_prepare_peft_lora_dir_rejects_file_path(tmp_path):
    runner = _load_runner_module()
    mock_file = tmp_path / "lora.mock.json"
    mock_file.write_text("{}", encoding="utf-8")

    peft_dir, missing = runner.prepare_peft_lora_dir(mock_file, tmp_path / "scratch")

    assert peft_dir is None
    assert any("expected LoRA directory" in item for item in missing)
