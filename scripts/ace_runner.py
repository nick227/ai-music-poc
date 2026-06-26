#!/usr/bin/env python3
"""
Bridge between our app's ACE_COMMAND_TEMPLATE and ACE-Step cli.py.

Our app calls:
  $python $script --prompt-file $prompt_file --lyrics-file $lyrics_file
    --output $output_path --duration $duration_seconds --seed $seed
    --guidance-scale $guidance_scale --model-dir $model_dir --device $device

This script translates those to ACE-Step cli.py arguments.
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

ACE_STEP_DIR = Path(os.environ.get("ACE_STEP_DIR", Path(__file__).resolve().parent.parent.parent / "models" / "ACE-Step-1.5"))
ACE_VENV = ACE_STEP_DIR / ".venv" / "bin" / "python"
ACE_CLI = ACE_STEP_DIR / "cli.py"


def main() -> None:
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
    # Voice parameters (not used by ACE CLI directly but passed in template)
    parser.add_argument("--singing-voice", default="auto")
    parser.add_argument("--vocal-intensity", type=float, default=0.65)
    parser.add_argument("--vocal-style", default="")
    parser.add_argument("--dry-run", action="store_true", help="Validate wiring without running ACE-Step inference")
    args = parser.parse_args()

    if args.dry_run:
        print("[ace_runner] dry-run ok")
        print(f"  ACE_STEP_DIR={ACE_STEP_DIR} exists={ACE_STEP_DIR.exists()}")
        print(f"  ACE_VENV={ACE_VENV} exists={ACE_VENV.exists()}")
        print(f"  ACE_CLI={ACE_CLI} exists={ACE_CLI.exists()}")
        print(f"  HF_HOME={os.environ.get('HF_HOME', '')}")
        print(f"  HUGGINGFACE_HUB_CACHE={os.environ.get('HUGGINGFACE_HUB_CACHE', '')}")
        print(f"  TRANSFORMERS_CACHE={os.environ.get('TRANSFORMERS_CACHE', '')}")
        print(f"  DIFFUSERS_CACHE={os.environ.get('DIFFUSERS_CACHE', '')}")
        print(f"  ACESTEP_CHECKPOINTS_DIR={os.environ.get('ACESTEP_CHECKPOINTS_DIR', '')}")
        print(f"  voice={args.singing_voice} intensity={args.vocal_intensity} style={args.vocal_style!r}")
        missing = [label for label, path in [("ACE_STEP_DIR", ACE_STEP_DIR), ("ACE_VENV", ACE_VENV), ("ACE_CLI", ACE_CLI)] if not path.exists()]
        if missing:
            print(f"[ace_runner] missing paths: {', '.join(missing)}", file=sys.stderr)
            sys.exit(2)
        sys.exit(0)

    if not args.prompt_file or not args.lyrics_file or not args.output:
        parser.error("--prompt-file, --lyrics-file, and --output are required unless --dry-run is set")

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
            str(ACE_VENV),
            str(ACE_CLI),
            "--caption", caption,
            "--lyrics", str(lyrics_path),
            "--save_dir", save_dir,
            "--audio_format", "wav",
            "--duration", str(args.duration),
            "--guidance_scale", str(args.guidance_scale),
            "--device", args.device,
            "--no_thinking",  # skip LM step for speed
        ]
        if args.seed is not None and args.seed >= 0:
            cmd += ["--seed", str(args.seed)]
        if args.model_dir:
            cmd += ["--checkpoint_dir", args.model_dir]
        # Quality → inference_steps mapping
        steps_map = {"draft": 25, "balanced": 50, "high": 100}
        steps = steps_map.get(args.quality, 50)
        cmd += ["--inference_steps", str(steps)]

        print(f"[ace_runner] Running: {shlex.join(cmd)}", flush=True)
        result = subprocess.run(cmd, cwd=str(ACE_STEP_DIR), text=True)
        if result.returncode != 0:
            print(f"[ace_runner] ACE-Step exited with {result.returncode}", file=sys.stderr)
            sys.exit(result.returncode)

        # Find the generated WAV in save_dir
        wavs = list(Path(save_dir).glob("**/*.wav"))
        if not wavs:
            print("[ace_runner] ERROR: No WAV output found in save_dir", file=sys.stderr)
            sys.exit(1)
        wavs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(wavs[0]), str(output_path))
        print(f"[ace_runner] Wrote {output_path} ({output_path.stat().st_size} bytes)", flush=True)


if __name__ == "__main__":
    main()
