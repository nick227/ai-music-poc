import json
from pathlib import Path

from app.core.ace_checkpoint_layout import (
    describe_checkpoint_layout,
    dit_checkpoint_folder_ready,
    dit_checkpoint_ready,
)


def _write_sharded_layout(folder: Path, *, shard_count: int = 4, present: set[int] | None = None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    shard_names = [f"model-{i:05d}-of-{shard_count:05d}.safetensors" for i in range(1, shard_count + 1)]
    weight_map = {f"layer.{i}.weight": shard_names[i % shard_count] for i in range(shard_count)}
    index = {"metadata": {"total_size": 1}, "weight_map": weight_map}
    (folder / "model.safetensors.index.json").write_text(json.dumps(index), encoding="utf-8")
    for idx, name in enumerate(shard_names, start=1):
        if present is None or idx in present:
            (folder / name).write_bytes(b"x" * 16)


def test_single_file_checkpoint_ready(tmp_path: Path) -> None:
    folder = tmp_path / "acestep-v15-turbo"
    folder.mkdir()
    (folder / "model.safetensors").write_bytes(b"x" * 32)
    assert dit_checkpoint_folder_ready(folder) is True
    assert describe_checkpoint_layout(folder) == "single model.safetensors"


def test_sharded_checkpoint_ready_when_complete(tmp_path: Path) -> None:
    folder = tmp_path / "acestep-v15-xl-sft"
    _write_sharded_layout(folder, shard_count=4)
    assert dit_checkpoint_folder_ready(folder) is True
    assert describe_checkpoint_layout(folder) == "sharded 4/4 shards"


def test_sharded_checkpoint_not_ready_when_incomplete(tmp_path: Path) -> None:
    folder = tmp_path / "acestep-v15-xl-sft"
    _write_sharded_layout(folder, shard_count=4, present={1, 2})
    assert dit_checkpoint_folder_ready(folder) is False
    assert describe_checkpoint_layout(folder) == "sharded 2/4 shards"


def test_dit_checkpoint_ready_by_name(tmp_path: Path) -> None:
    _write_sharded_layout(tmp_path / "acestep-v15-xl-sft", shard_count=4)
    assert dit_checkpoint_ready(tmp_path, "acestep-v15-xl-sft") is True
    assert dit_checkpoint_ready(tmp_path, "acestep-v15-turbo") is False


def test_empty_folder_not_ready(tmp_path: Path) -> None:
    folder = tmp_path / "empty"
    folder.mkdir()
    assert dit_checkpoint_folder_ready(folder) is False
    assert describe_checkpoint_layout(folder) == "weights missing"
