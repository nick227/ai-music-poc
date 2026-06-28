"""Detect whether an ACE DiT checkpoint folder has loadable weights (single-file or sharded)."""
from __future__ import annotations

import json
import re
from pathlib import Path

_SHARD_NAME_RE = re.compile(r"^model-\d+-of-\d+\.safetensors$")


def _nonempty_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _single_file_ready(folder: Path) -> bool:
    return _nonempty_file(folder / "model.safetensors")


def _sharded_files(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and _SHARD_NAME_RE.match(p.name) and p.stat().st_size > 0
    )


def _expected_shard_names(index_path: Path) -> set[str]:
    data = json.loads(index_path.read_text(encoding="utf-8"))
    weight_map = data.get("weight_map")
    if not isinstance(weight_map, dict):
        return set()
    return {str(v) for v in weight_map.values() if str(v).endswith(".safetensors")}


def _sharded_weights_ready(folder: Path) -> bool:
    index_path = folder / "model.safetensors.index.json"
    if not _nonempty_file(index_path):
        return False
    shards = _sharded_files(folder)
    if not shards:
        return False
    present = {p.name for p in shards}
    try:
        expected = _expected_shard_names(index_path)
        if expected:
            return expected <= present
    except (json.JSONDecodeError, OSError):
        pass
    return True


def dit_checkpoint_folder_ready(folder: Path) -> bool:
    """True when folder has a single model.safetensors or a complete sharded layout."""
    if not folder.is_dir():
        return False
    if _single_file_ready(folder):
        return True
    return _sharded_weights_ready(folder)


def dit_checkpoint_ready(checkpoint_dir: Path, name: str) -> bool:
    return dit_checkpoint_folder_ready(checkpoint_dir / name)


def describe_checkpoint_layout(folder: Path) -> str:
    """Human-readable layout summary for doctor/readiness output."""
    if not folder.is_dir():
        return "missing"
    if _single_file_ready(folder):
        return "single model.safetensors"
    index_path = folder / "model.safetensors.index.json"
    shards = _sharded_files(folder)
    if index_path.is_file() and shards:
        try:
            expected = _expected_shard_names(index_path)
            if expected:
                present = {p.name for p in shards}
                return f"sharded {len(present & expected)}/{len(expected)} shards"
        except (json.JSONDecodeError, OSError):
            pass
        return f"sharded {len(shards)} shard(s)"
    return "weights missing"
