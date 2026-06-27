#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from app.core.audio_validation import validate_wav_output
from app.core.config import get_settings
from app.domain.models import GenerationRequest
from app.generators.ace_step.command_builder import AceCommandBuilder
from app.generators.ace_step.env import ace_subprocess_env
from app.generators.ace_step.health import (
    check_ace_packages,
    get_ace_status,
    recommended_actions,
    run_ace_python_diagnostic,
    run_ace_runner_dry_run,
)

DEFAULT_KEPT_OUTPUT = ROOT / "data" / "model_outputs" / "ace-smoke-test.wav"


def resolve_output_path(output: str | None, keep_output: bool) -> Path | None:
    if output:
        path = Path(output).expanduser()
        return path if path.is_absolute() else ROOT / path
    if keep_output:
        return DEFAULT_KEPT_OUTPUT
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ACE-Step command setup for AI Music POC")
    parser.add_argument("--run-generation", action="store_true", help="Run ACE_COMMAND_TEMPLATE and validate the WAV")
    parser.add_argument("--dry-run-only", action="store_true", help="Run package + runner dry-run checks only")
    parser.add_argument("--keep-output", action="store_true", help=f"Preserve generated WAV at {DEFAULT_KEPT_OUTPUT.relative_to(ROOT)}")
    parser.add_argument("--output", help="Preserve generated WAV at this path. Relative paths are resolved from the project root.")
    parser.add_argument("--duration", type=int, default=10)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()
    status = get_ace_status(settings)
    diagnostic = run_ace_python_diagnostic(settings)
    packages = check_ace_packages(settings)
    dry_run = run_ace_runner_dry_run(settings)
    actions = recommended_actions(status, diagnostic, packages, dry_run)

    print("== ACE status ==")
    print(status.model_dump_json(indent=2))
    print("\n== Python diagnostic ==")
    print(json.dumps(diagnostic, indent=2, default=str))
    print("\n== Package check ==")
    print(json.dumps(packages, indent=2, default=str))
    print("\n== Runner dry-run ==")
    print(json.dumps(dry_run, indent=2, default=str))
    print("\n== Recommended actions ==")
    for action in actions:
        print(f"  - {action}")

    if args.dry_run_only:
        ok = bool(packages.get("ok")) and bool(dry_run.get("ok"))
        return 0 if ok else 2

    if not status.can_generate:
        print("\nACE is not ready. Fix the warnings above before running generation.")
        return 2

    request = GenerationRequest(
        title="ACE smoke test",
        prompt="short dark disco test, simple beat, clear vocal demo",
        lyrics="Verse:\nThis is only a smoke test\nChorus:\nMake a tiny song",
        generator="ace-step-command",
        duration_seconds=args.duration,
        seed=1234,
        singing_voice="female",
        vocal_intensity=0.75,
        allow_fallback=False,
    )
    preserved_output_path = resolve_output_path(args.output, args.keep_output)
    context = nullcontext(None) if preserved_output_path else tempfile.TemporaryDirectory()
    with context as tmp:
        output_path = preserved_output_path or Path(str(tmp)) / "ace-smoke-test.wav"
        output_is_temporary = preserved_output_path is None
        if not output_is_temporary:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        command = AceCommandBuilder(settings).build(request, output_path)
        print("\n== Output ==")
        print(f"path: {output_path}")
        print(f"temporary: {str(output_is_temporary).lower()}")
        print("\n== Rendered command ==")
        print(" ".join(command))
        if not args.run_generation:
            print("\nRendered command only. Re-run with --run-generation to execute model inference.")
            return 0
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=settings.ace_timeout_seconds,
            check=False,
            env=ace_subprocess_env(settings),
        )
        print("\n== Subprocess ==")
        print(json.dumps({"returncode": completed.returncode, "stdout_tail": completed.stdout[-2000:], "stderr_tail": completed.stderr[-2000:]}, indent=2))
        if completed.returncode != 0:
            return completed.returncode or 1
        audio = validate_wav_output(output_path, expected_duration_seconds=args.duration)
        print("\n== Audio validation ==")
        print(json.dumps(audio.__dict__, indent=2, default=str))
        print("\n== Final output ==")
        print(f"path: {output_path}")
        print(f"preserved: {str(not output_is_temporary).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
