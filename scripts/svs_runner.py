#!/usr/bin/env python3
"""Render mock or external SVS vocal stems from svs_score.json."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.audio_validation import validate_wav_output
from app.generators.svs.mock_audio import render_score_to_wav
from app.generators.svs.plan_export import load_svs_score

DEFAULT_EXTERNAL_COMMAND = ""


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score", type=Path, required=True, help="Path to svs_score.json")
    parser.add_argument("--output", type=Path, required=True, help="Output vocal stem WAV path")
    parser.add_argument(
        "--backend",
        choices=("mock", "external"),
        default="mock",
        help="mock = sine-burst debug stem; external = SVS_EXTERNAL_COMMAND shell template",
    )
    parser.add_argument(
        "--external-command",
        default=DEFAULT_EXTERNAL_COMMAND,
        help="Shell command with {score_path} and {output_path} placeholders",
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
    }

    if args.backend == "mock":
        render_score_to_wav(score, output_path)
        audio = validate_wav_output(output_path)
        report["ok"] = True
        report["sample_rate"] = audio.sample_rate
    else:
        command = args.external_command.strip()
        if not command:
            report["ok"] = False
            report["error"] = "external backend requires --external-command or SVS_EXTERNAL_COMMAND"
            if args.report:
                args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(report["error"], file=sys.stderr)
            return 2
        code, stdout, stderr = _run_external(command, score_path, output_path)
        report["returncode"] = code
        report["stdout_tail"] = stdout[-2000:]
        report["stderr_tail"] = stderr[-2000:]
        if code != 0 or not output_path.exists():
            report["ok"] = False
            report["error"] = stderr.strip() or stdout.strip() or f"exit {code}"
            if args.report:
                args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(report["error"], file=sys.stderr)
            return code or 1
        audio = validate_wav_output(output_path)
        report["ok"] = True
        report["sample_rate"] = audio.sample_rate

    if args.report:
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"ok": report["ok"], "output": str(output_path), "backend": args.backend}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
