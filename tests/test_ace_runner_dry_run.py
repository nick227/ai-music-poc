from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "ace_runner.py"


def _load_runner_module():
    spec = importlib.util.spec_from_file_location("ace_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _stub_ace_tree(base: Path) -> Path:
    step_dir = base / "ACE-Step-1.5"
    (step_dir / ".venv" / "bin").mkdir(parents=True)
    (step_dir / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    (step_dir / "cli.py").write_text("# stub\n", encoding="utf-8")
    return step_dir


def test_dry_run_lines_include_hf_cache_and_resolved_args(tmp_path, monkeypatch):
    runner = _load_runner_module()
    step_dir = _stub_ace_tree(tmp_path)
    monkeypatch.setenv("ACE_STEP_DIR", str(step_dir))
    monkeypatch.setenv("HF_HOME", "/cache/hf")
    monkeypatch.setenv("HUGGINGFACE_HUB_CACHE", "/cache/hf/hub")
    monkeypatch.setenv("TRANSFORMERS_CACHE", "/cache/hf/transformers")
    monkeypatch.setenv("DIFFUSERS_CACHE", "/cache/hf/diffusers")
    monkeypatch.setenv("ACESTEP_CHECKPOINTS_DIR", "/cache/hf/ace-step-checkpoints")

    prompt = tmp_path / "prompt.txt"
    lyrics = tmp_path / "lyrics.txt"
    request = tmp_path / "request.json"
    output = tmp_path / "out.wav"
    model_dir = tmp_path / "checkpoints"
    model_dir.mkdir()
    prompt.write_text("dark disco", encoding="utf-8")
    lyrics.write_text("hello world", encoding="utf-8")
    request.write_text("{}", encoding="utf-8")

    args = runner.build_parser().parse_args([
        "--dry-run",
        "--prompt-file", str(prompt),
        "--lyrics-file", str(lyrics),
        "--request-file", str(request),
        "--output", str(output),
        "--model-dir", str(model_dir),
        "--device", "cuda",
        "--duration", "10",
        "--seed", "42",
    ])
    text = "\n".join(runner.dry_run_lines(args))
    assert "ACE_STEP_DIR=" in text
    assert "HF_HOME=/cache/hf" in text
    assert "HUGGINGFACE_HUB_CACHE=/cache/hf/hub" in text
    assert "TRANSFORMERS_CACHE=/cache/hf/transformers" in text
    assert "DIFFUSERS_CACHE=/cache/hf/diffusers" in text
    assert "ACESTEP_CHECKPOINTS_DIR=/cache/hf/ace-step-checkpoints" in text
    assert "prompt_file=" in text and "chars=10" in text
    assert "lyrics_file=" in text
    assert "request_file=" in text
    assert f"output={output.resolve()}" in text
    assert "device=cuda" in text


def test_dry_run_exits_zero_without_torch(tmp_path, monkeypatch):
    step_dir = _stub_ace_tree(tmp_path)
    env = os.environ.copy()
    env["ACE_STEP_DIR"] = str(step_dir)
    env["HF_HOME"] = "/cache/hf"
    completed = subprocess.run(
        [sys.executable, str(RUNNER), "--dry-run"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "dry-run ok" in completed.stdout
    assert "HF_HOME=/cache/hf" in completed.stdout
    assert "torch" not in completed.stderr.lower()


def test_dry_run_missing_paths_exit_two(tmp_path, monkeypatch):
    runner = _load_runner_module()
    missing_dir = tmp_path / "missing"
    monkeypatch.setenv("ACE_STEP_DIR", str(missing_dir))
    args = runner.build_parser().parse_args(["--dry-run"])
    assert runner.run_dry_run(args) == 2


def test_seed_flag_without_value_parses_as_none():
    runner = _load_runner_module()
    args = runner.build_parser().parse_args(["--seed", "--guidance-scale", "7.5"])
    assert args.seed is None
    assert args.guidance_scale == 7.5
