from __future__ import annotations

import json

import pytest

from app.generators.ace_step.lora_meta import (
    ace_meta_sidecar_path,
    lora_meta_from_sources,
    parse_lora_meta_from_stdout,
    read_ace_meta_sidecar,
)


def test_parse_lora_meta_from_stdout_line():
    stdout = '[ace_runner] lora_meta={"loraLoadAttempted":true,"loraLoadSucceeded":true,"loraLoadMessage":"ok","loraPath":"/tmp/final","loraScale":1.0}\n'
    meta = parse_lora_meta_from_stdout(stdout)
    assert meta["loraLoadAttempted"] is True
    assert meta["loraLoadSucceeded"] is True
    assert meta["loraPath"] == "/tmp/final"


def test_read_ace_meta_sidecar(tmp_path):
    output = tmp_path / "job.wav"
    sidecar = ace_meta_sidecar_path(output)
    payload = {
        "loraLoadAttempted": True,
        "loraLoadSucceeded": True,
        "loraLoadMessage": "loaded",
        "loraPath": "/tmp/final",
        "loraScale": 0.8,
    }
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    assert read_ace_meta_sidecar(output) == payload
    assert lora_meta_from_sources(output_path=output, stdout="", stderr="") == payload


def test_lora_meta_from_stdout_fallback():
    stdout = "[ace_runner] load_lora: Adapter loaded\n"
    meta = lora_meta_from_sources(output_path=__import__("pathlib").Path("/missing.wav"), stdout=stdout, stderr="")
    assert meta["loraLoadAttempted"] is True
    assert meta["loraLoadMessage"] == "Adapter loaded"
