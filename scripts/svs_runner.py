#!/usr/bin/env python3
"""Render mock or external SVS vocal stems from svs_score.json."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.audio_validation import validate_wav_output
from app.generators.svs.diffsinger import save_ds_file, score_to_ds
from app.generators.svs.mock_audio import render_score_to_wav
from app.generators.svs.plan_export import load_svs_score

DEFAULT_EXTERNAL_COMMAND = ""
_DIFFSINGER_INFER_SCRIPTS = ("scripts/infer.py", "inference/svs/ds_e2e.py")
# Our standalone ONNX inference script for TIGER-style packs
_DIFFSINGER_ONNX_SCRIPT = Path(__file__).resolve().parent / "diffsinger_infer.py"

# Library path required for onnxruntime-gpu with CUDA 13 + cuDNN 9 (from ltx-env)
_LTX_NVIDIA = Path.home() / "web/ltx-env/.venv/lib/python3.12/site-packages/nvidia"
_CUDA_LIB_DIRS = [
    str(_LTX_NVIDIA / "cu13/lib"),
    str(_LTX_NVIDIA / "cudnn/lib"),
    str(_LTX_NVIDIA / "cuda_runtime/lib"),
]


def _run_external(command: str, score_path: Path, output_path: Path) -> tuple[int, str, str]:
    rendered = command.format(score_path=score_path, output_path=output_path)
    completed = subprocess.run(
        rendered,
        shell=True,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def _find_diffsinger_infer(repo: Path) -> Path | None:
    for rel in _DIFFSINGER_INFER_SCRIPTS:
        candidate = repo / rel
        if candidate.exists():
            return candidate
    return None


def _find_diffsinger_config(repo: Path, model_dir: Path) -> Path | None:
    for search_root in (model_dir, repo / "configs" / "acoustic"):
        for yaml in sorted(search_root.glob("*.yaml")):
            return yaml
    return None


def _run_diffsinger(
    score_path: Path,
    output_path: Path,
    repo: Path,
    config: Path | None,
    python: str,
    timeout: int,
    tiger_dir: Path | None = None,
    speaker: str = "tiger_fresh",
    depth: float = 0.6,
    steps: int = 20,
) -> tuple[int, str, str]:
    # Fast path: TIGER-style ONNX pack via our standalone inference script.
    if tiger_dir is not None and tiger_dir.exists() and _DIFFSINGER_ONNX_SCRIPT.exists():
        import os as _os
        env = {**_os.environ}
        ld = ":".join(d for d in _CUDA_LIB_DIRS if Path(d).exists())
        if ld:
            env["LD_LIBRARY_PATH"] = ld + ":" + env.get("LD_LIBRARY_PATH", "")
        cmd = [
            python,
            str(_DIFFSINGER_ONNX_SCRIPT),
            "--ds", str(output_path.with_suffix(".ds")),
            "--output", str(output_path),
            "--tiger-dir", str(tiger_dir),
            "--speaker", speaker,
            "--depth", str(depth),
            "--steps", str(steps),
        ]
        try:
            result = subprocess.run(
                cmd, text=True, capture_output=True, timeout=timeout, check=False, env=env
            )
        except subprocess.TimeoutExpired:
            return 1, "", f"DiffSinger ONNX inference timed out after {timeout}s"
        return result.returncode, result.stdout[-2000:], result.stderr[-2000:]

    # Fallback: openvpi/DiffSinger Python training repo (expects PyTorch checkpoint).
    infer_script = _find_diffsinger_infer(repo)
    if infer_script is None:
        tried = ", ".join(_DIFFSINGER_INFER_SCRIPTS)
        return 1, "", f"DiffSinger inference script not found in {repo} (tried: {tried})"

    if config is None:
        return 1, "", (
            "No DiffSinger config YAML found. "
            "Pass --diffsinger-config or place a *.yaml in --model-dir."
        )

    save_dir = output_path.parent / f"{output_path.stem}_ds_out"
    save_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        python,
        str(infer_script),
        "--config", str(config),
        "--ds_path", str(output_path.with_suffix(".ds")),
        "--save_path", str(save_dir),
    ]
    try:
        result = subprocess.run(
            cmd, cwd=str(repo), text=True, capture_output=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return 1, "", f"DiffSinger inference timed out after {timeout}s"

    if result.returncode != 0 or not any(save_dir.glob("*.wav")):
        return result.returncode, result.stdout[-2000:], result.stderr[-2000:]

    wav_files = sorted(save_dir.glob("*.wav"))
    shutil.copy(wav_files[0], output_path)
    return 0, result.stdout[-2000:], result.stderr[-2000:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score", type=Path, required=True, help="Path to svs_score.json")
    parser.add_argument("--output", type=Path, required=True, help="Output vocal stem WAV path")
    parser.add_argument(
        "--backend",
        choices=("mock", "external", "diffsinger"),
        default="mock",
        help=(
            "mock = sine-burst debug stem; "
            "external = shell template via --external-command; "
            "diffsinger = DiffSinger inference via --diffsinger-repo"
        ),
    )
    parser.add_argument(
        "--external-command",
        default=DEFAULT_EXTERNAL_COMMAND,
        help="Shell command with {score_path} and {output_path} placeholders (external backend)",
    )
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=Path("./data/svs_models"),
        help="SVS model directory; used for DiffSinger config YAML discovery (SVS_MODEL_DIR)",
    )
    parser.add_argument(
        "--diffsinger-repo",
        type=Path,
        default=None,
        help="Path to a cloned openvpi/DiffSinger repository",
    )
    parser.add_argument(
        "--diffsinger-config",
        type=Path,
        default=None,
        help="Path to DiffSinger acoustic config YAML (overrides auto-discovery)",
    )
    parser.add_argument(
        "--diffsinger-python",
        default=sys.executable,
        help="Python interpreter to use for DiffSinger inference (default: current interpreter)",
    )
    parser.add_argument(
        "--tiger-dir",
        type=Path,
        default=None,
        help="Path to extracted TIGER ONNX voice pack (enables fast ONNX path)",
    )
    parser.add_argument(
        "--speaker",
        default="tiger_fresh",
        choices=["tiger_fresh", "tiger_disco", "tiger_electric",
                 "tiger_vinyl", "tiger_glam", "tiger_mystic", "tiger_royal"],
        help="Speaker/style for TIGER ONNX inference",
    )
    parser.add_argument("--depth", type=float, default=0.6, help="Diffusion depth 0.0–1.0")
    parser.add_argument("--steps", type=int, default=20, help="Diffusion steps")
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Subprocess timeout in seconds (SVS_TIMEOUT_SECONDS)",
    )
    parser.add_argument("--report", type=Path, help="Optional JSON status report path")
    args = parser.parse_args()

    score_path = args.score.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    score = load_svs_score(score_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, object] = {
        "backend": args.backend,
        "score_path": str(score_path),
        "output_path": str(output_path),
        "note_count": len(score.note_events()),
        "rest_count": len(score.rest_events()),
        "bpm": score.bpm,
        "duration_beats": score.duration_beats,
    }

    if args.backend == "mock":
        render_score_to_wav(score, output_path)
        audio = validate_wav_output(output_path)
        report["ok"] = True
        report["sample_rate"] = audio.sample_rate

    elif args.backend == "diffsinger":
        # Write .ds file alongside the output for inspection.
        ds_path = output_path.with_suffix(".ds")
        save_ds_file(score, ds_path)
        segments = score_to_ds(score)
        report["ds_path"] = str(ds_path)
        report["ds_segments"] = len(segments)

        tiger_dir = args.tiger_dir
        if tiger_dir:
            report["tiger_dir"] = str(tiger_dir.expanduser().resolve())
            report["speaker"] = args.speaker

        repo = args.diffsinger_repo
        use_onnx_path = (
            tiger_dir is not None
            and tiger_dir.expanduser().exists()
            and _DIFFSINGER_ONNX_SCRIPT.exists()
        )
        if not use_onnx_path and (repo is None or not repo.exists()):
            report["ok"] = False
            report["error"] = (
                f"DiffSinger repo not found at {repo!r}. "
                "Clone openvpi/DiffSinger and pass --diffsinger-repo, "
                "or provide --tiger-dir for ONNX inference."
            )
            _write_report(report, args.report)
            print(report["error"], file=sys.stderr)
            return 2

        model_dir = args.model_dir.expanduser().resolve()
        config = (
            args.diffsinger_config.expanduser().resolve()
            if args.diffsinger_config
            else (_find_diffsinger_config(repo, model_dir) if repo else None)
        )
        if repo:
            report["diffsinger_repo"] = str(repo)
            report["diffsinger_config"] = str(config) if config else None

        code, stdout, stderr = _run_diffsinger(
            score_path, output_path, repo or Path("."), config,
            args.diffsinger_python, args.timeout,
            tiger_dir=args.tiger_dir,
            speaker=args.speaker,
            depth=args.depth,
            steps=args.steps,
        )
        report["returncode"] = code
        report["stdout_tail"] = stdout
        report["stderr_tail"] = stderr

        if code != 0 or not output_path.exists():
            report["ok"] = False
            report["error"] = stderr.strip() or stdout.strip() or f"DiffSinger exited {code}"
            _write_report(report, args.report)
            print(report["error"], file=sys.stderr)
            return code or 1

        audio = validate_wav_output(output_path)
        report["ok"] = True
        report["sample_rate"] = audio.sample_rate

    else:  # external
        command = args.external_command.strip()
        if not command:
            report["ok"] = False
            report["error"] = "external backend requires --external-command"
            _write_report(report, args.report)
            print(report["error"], file=sys.stderr)
            return 2
        code, stdout, stderr = _run_external(command, score_path, output_path)
        report["returncode"] = code
        report["stdout_tail"] = stdout[-2000:]
        report["stderr_tail"] = stderr[-2000:]
        if code != 0 or not output_path.exists():
            report["ok"] = False
            report["error"] = stderr.strip() or stdout.strip() or f"exit {code}"
            _write_report(report, args.report)
            print(report["error"], file=sys.stderr)
            return code or 1
        audio = validate_wav_output(output_path)
        report["ok"] = True
        report["sample_rate"] = audio.sample_rate

    _write_report(report, args.report)
    print(json.dumps({"ok": report["ok"], "output": str(output_path), "backend": args.backend}))
    return 0


def _write_report(report: dict, path: Path | None) -> None:
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
