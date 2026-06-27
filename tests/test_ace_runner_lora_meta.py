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
