from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_LORA_META_LINE = re.compile(r"^\[ace_runner\]\s*lora_meta=(\{.*\})\s*$", re.MULTILINE)


def ace_meta_sidecar_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}.ace_meta.json")


def empty_lora_meta(*, lora_path: str | None = None, lora_scale: float | None = None) -> dict[str, Any]:
    return {
        "loraLoadAttempted": False,
        "loraLoadSucceeded": False,
        "loraLoadMessage": "",
        "loraPath": lora_path or "",
        "loraScale": lora_scale,
    }


def read_ace_meta_sidecar(output_path: Path) -> dict[str, Any]:
    path = ace_meta_sidecar_path(output_path)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def parse_lora_meta_from_stdout(stdout: str) -> dict[str, Any]:
    match = _LORA_META_LINE.search(stdout)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def lora_meta_from_sources(*, output_path: Path, stdout: str, stderr: str = "") -> dict[str, Any]:
    sidecar = read_ace_meta_sidecar(output_path)
    if sidecar:
        return sidecar
    parsed = parse_lora_meta_from_stdout(stdout)
    if parsed:
        return parsed
    combined = f"{stdout}\n{stderr}"
    if "[ace_runner] load_lora:" in combined:
        for line in combined.splitlines():
            if "[ace_runner] load_lora:" in line:
                message = line.split("[ace_runner] load_lora:", 1)[1].strip()
                return {
                    "loraLoadAttempted": True,
                    "loraLoadSucceeded": bool(message) and "fail" not in message.lower(),
                    "loraLoadMessage": message,
                    "loraPath": "",
                    "loraScale": None,
                }
    return {}
