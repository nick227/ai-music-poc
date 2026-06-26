#!/usr/bin/env python3
"""
Bridge between our app's ACE_COMMAND_TEMPLATE and ACE-Step cli.py.

Dry-run mode validates wiring only — no torch/transformers/diffusers imports.
"""
from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_ACE_STEP_DIR = Path(__file__).resolve().parent.parent.parent / "models" / "ACE-Step-1.5"


def ace_step_dir() -> Path:
    return Path(os.environ.get("ACE_STEP_DIR", str(DEFAULT_ACE_STEP_DIR))).expanduser().resolve()


def ace_venv_python(step_dir: Path) -> Path:
    return (step_dir / ".venv" / "bin" / "python").resolve()


def ace_cli_script(step_dir: Path) -> Path:
    return (step_dir / "cli.py").resolve()


def resolve_optional_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def file_summary(path: Path | None) -> str:
    if path is None:
        return "(not set)"
    if not path.exists():
        return f"{path} exists=False"
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            return f"{path} exists=True chars={len(text)}"
        except OSError:
            return f"{path} exists=True bytes={path.stat().st_size}"
    return f"{path} exists=True"


def dry_run_lines(args: argparse.Namespace) -> list[str]:
    step_dir = ace_step_dir()
    venv_python = ace_venv_python(step_dir)
    cli_script = ace_cli_script(step_dir)

    prompt_file = resolve_optional_path(args.prompt_file)
    lyrics_file = resolve_optional_path(args.lyrics_file)
    negative_file = resolve_optional_path(args.negative_prompt_file or args.negative_file)
    request_file = resolve_optional_path(args.request_file)
    output_path = resolve_optional_path(args.output)
    model_dir = resolve_optional_path(args.model_dir)

    lines = [
        "[ace_runner] dry-run ok",
        "",
        "== ACE paths ==",
        f"ACE_STEP_DIR={step_dir} exists={step_dir.exists()}",
        f"ACE_VENV={venv_python} exists={venv_python.exists()}",
        f"ACE_CLI={cli_script} exists={cli_script.exists()}",
        "",
        "== Hugging Face cache (subprocess env) ==",
        f"HF_HOME={os.environ.get('HF_HOME', '')}",
        f"HUGGINGFACE_HUB_CACHE={os.environ.get('HUGGINGFACE_HUB_CACHE', '')}",
        f"TRANSFORMERS_CACHE={os.environ.get('TRANSFORMERS_CACHE', '')}",
        f"DIFFUSERS_CACHE={os.environ.get('DIFFUSERS_CACHE', '')}",
        f"ACESTEP_CHECKPOINTS_DIR={os.environ.get('ACESTEP_CHECKPOINTS_DIR', '')}",
        "",
        "== Resolved request args ==",
        f"prompt_file={file_summary(prompt_file)}",
        f"lyrics_file={file_summary(lyrics_file)}",
        f"negative_prompt_file={file_summary(negative_file)}",
        f"request_file={file_summary(request_file)}",
        f"output={output_path if output_path else '(not set)'}",
        f"model_dir={model_dir} exists={model_dir.exists() if model_dir else False}",
        f"device={args.device}",
        f"duration={args.duration} seed={args.seed} quality={args.quality} guidance_scale={args.guidance_scale}",
        "",
        "== Voice passthrough (app template only; ACE CLI ignores today) ==",
        f"singing_voice={args.singing_voice} vocal_intensity={args.vocal_intensity} vocal_style={args.vocal_style!r}",
    ]
    return lines


def missing_dry_run_paths() -> list[str]:
    step_dir = ace_step_dir()
    missing: list[str] = []
    for label, path in [
        ("ACE_STEP_DIR", step_dir),
        ("ACE_VENV", ace_venv_python(step_dir)),
        ("ACE_CLI", ace_cli_script(step_dir)),
    ]:
        if not path.exists():
            missing.append(label)
    return missing


def run_dry_run(args: argparse.Namespace) -> int:
    for line in dry_run_lines(args):
        print(line)
    missing = missing_dry_run_paths()
    if missing:
        print(f"[ace_runner] missing paths: {', '.join(missing)}", file=sys.stderr)
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ACE-Step runner bridge")
    parser.add_argument("--prompt-file")
    parser.add_argument("--lyrics-file")
    parser.add_argument("--negative-file")
    parser.add_argument("--negative-prompt-file")
    parser.add_argument("--request-file")
    parser.add_argument("--output")
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--guidance-scale", type=float, default=7.5)
    parser.add_argument("--quality", default="balanced")
    parser.add_argument("--model-dir")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--singing-voice", default="auto")
    parser.add_argument("--vocal-intensity", type=float, default=0.65)
    parser.add_argument("--vocal-style", default="")
    parser.add_argument("--dry-run", action="store_true", help="Validate wiring without running ACE-Step inference")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.dry_run:
        return run_dry_run(args)

    if not args.prompt_file or not args.lyrics_file or not args.output:
        build_parser().error("--prompt-file, --lyrics-file, and --output are required unless --dry-run is set")

    step_dir = ace_step_dir()
    venv_python = ace_venv_python(step_dir)
    cli_script = ace_cli_script(step_dir)

    negative_file = args.negative_prompt_file or args.negative_file
    caption = Path(args.prompt_file).read_text(encoding="utf-8").strip()
    lyrics_path = Path(args.lyrics_file)
    output_path = Path(args.output)
    if negative_file and Path(negative_file).exists():
        negative = Path(negative_file).read_text(encoding="utf-8").strip()
        if negative:
            caption = f"{caption}\n\nAvoid: {negative}"

    with tempfile.TemporaryDirectory(prefix="ace_out_") as save_dir:
        cmd: list[str] = [
            str(venv_python),
            str(cli_script),
            "--caption", caption,
            "--lyrics", str(lyrics_path),
            "--save_dir", save_dir,
            "--audio_format", "wav",
            "--duration", str(args.duration),
            "--guidance_scale", str(args.guidance_scale),
            "--device", args.device,
            "--no_thinking",
        ]
        if args.seed is not None and args.seed >= 0:
            cmd += ["--seed", str(args.seed)]
        if args.model_dir:
            cmd += ["--checkpoint_dir", args.model_dir]
        steps_map = {"draft": 25, "balanced": 50, "high": 100}
        cmd += ["--inference_steps", str(steps_map.get(args.quality, 50))]

        print(f"[ace_runner] Running: {shlex.join(cmd)}", flush=True)
        result = subprocess.run(cmd, cwd=str(step_dir), text=True)
        if result.returncode != 0:
            print(f"[ace_runner] ACE-Step exited with {result.returncode}", file=sys.stderr)
            return result.returncode

        wavs = list(Path(save_dir).glob("**/*.wav"))
        if not wavs:
            print("[ace_runner] ERROR: No WAV output found in save_dir", file=sys.stderr)
            return 1
        wavs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(wavs[0]), str(output_path))
        print(f"[ace_runner] Wrote {output_path} ({output_path.stat().st_size} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
