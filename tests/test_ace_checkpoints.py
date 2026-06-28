from pathlib import Path

from app.generators.ace_step.checkpoints import resolve_generation_plan


def test_balanced_uses_sft_when_installed(tmp_path: Path) -> None:
    (tmp_path / "acestep-v15-turbo").mkdir()
    (tmp_path / "acestep-v15-sft").mkdir()
    checkpoint, steps, is_turbo = resolve_generation_plan(quality="balanced", checkpoint_dir=tmp_path)
    assert checkpoint == "acestep-v15-sft"
    assert steps == 24
    assert is_turbo is False


def test_high_uses_fifty_steps_with_sft(tmp_path: Path) -> None:
    (tmp_path / "acestep-v15-sft").mkdir()
    checkpoint, steps, is_turbo = resolve_generation_plan(quality="high", checkpoint_dir=tmp_path)
    assert checkpoint == "acestep-v15-sft"
    assert steps == 50
    assert is_turbo is False


def test_turbo_only_clamps_steps(tmp_path: Path) -> None:
    (tmp_path / "acestep-v15-turbo").mkdir()
    checkpoint, steps, is_turbo = resolve_generation_plan(quality="balanced", checkpoint_dir=tmp_path)
    assert checkpoint == "acestep-v15-turbo"
    assert steps == 8
    assert is_turbo is True
