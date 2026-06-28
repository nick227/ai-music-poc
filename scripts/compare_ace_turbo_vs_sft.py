#!/usr/bin/env python3
"""Compare turbo 8-step vs SFT 24/50-step ACE generation on identical inputs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

from app.core.ace_profiles import FINAL_SFT_CHECKPOINT, build_final_sft_profile, final_sft_installed
from app.core.ace_runtime import validate_with_ffprobe
from app.core.audio_validation import validate_wav_output
from app.core.config import get_settings
from app.generators.ace_step.env import ace_subprocess_env

DEFAULT_PROMPT = "ambient ocean waves, soft pads, gentle rhythm, cinematic"
DEFAULT_LYRICS = "[Instrumental]"
DEFAULT_SEED = 4242
DEFAULT_DURATION = 30

TURBO_VARIANT = {
    "id": "turbo_8",
    "label": "turbo 8 steps",
    "checkpoint": "acestep-v15-turbo",
    "inference_steps": 8,
}
SFT_VARIANTS = (
    {"id": "sft_24", "label": "sft 24 steps", "checkpoint": FINAL_SFT_CHECKPOINT, "inference_steps": 24},
    {"id": "sft_50", "label": "sft 50 steps", "checkpoint": FINAL_SFT_CHECKPOINT, "inference_steps": 50},
)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_variants(*, include_sft: bool) -> list[dict[str, Any]]:
    variants = [TURBO_VARIANT]
    if include_sft:
        variants.extend(SFT_VARIANTS)
    return variants


def build_generation_command(
    *,
    ace_python: Path,
    ace_script: Path,
    prompt_file: Path,
    lyrics_file: Path,
    output_path: Path,
    model_dir: Path,
    device: str,
    seed: int,
    duration: int,
    checkpoint: str,
    inference_steps: int,
    offload_to_cpu: bool,
) -> list[str]:
    cmd = [
        str(ace_python),
        str(ace_script),
        "--prompt-file",
        str(prompt_file),
        "--lyrics-file",
        str(lyrics_file),
        "--output",
        str(output_path),
        "--model-dir",
        str(model_dir),
        "--duration",
        str(duration),
        "--seed",
        str(seed),
        "--guidance-scale",
        "7.5",
        "--quality",
        "balanced",
        "--device",
        device,
        "--config-path",
        checkpoint,
        "--inference-steps",
        str(inference_steps),
        "--batch-size",
        "1",
        "--use-lora",
        "false",
        "--lora-path",
        "__none__",
        "--lora-scale",
        "1.0",
        "--use-lm",
        "false",
    ]
    if offload_to_cpu:
        cmd.append("--offload-to-cpu")
    return cmd


def validate_generated_audio(
    path: Path,
    *,
    ffprobe: str,
    expected_duration_seconds: int,
    min_duration_ratio: float = 0.85,
) -> dict[str, Any]:
    probe = validate_with_ffprobe(path, ffprobe=ffprobe)
    min_duration = expected_duration_seconds * min_duration_ratio
    payload = probe.model_dump()
    payload["duration_at_least_expected"] = probe.duration_seconds >= min_duration
    payload["nonzero_size"] = probe.file_size_bytes > 0
    payload["ok"] = bool(probe.ok and payload["duration_at_least_expected"] and payload["nonzero_size"])
    try:
        wav = validate_wav_output(path, expected_duration_seconds=expected_duration_seconds)
        payload["rms"] = wav.rms
        payload["peak_abs_sample"] = wav.peak_abs_sample
        payload["wav_warnings"] = wav.warnings
    except Exception as exc:
        payload["rms"] = None
        payload["peak_abs_sample"] = None
        payload["wav_warnings"] = [str(exc)]
        payload["ok"] = False
    return payload


def _run_generation(
    command: list[str],
    *,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
    timeout: int,
) -> tuple[int, float]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            result = subprocess.run(
                command,
                cwd=str(ROOT),
                env=env,
                stdout=stdout,
                stderr=stderr,
                text=True,
                timeout=timeout,
                check=False,
            )
        return result.returncode, round(time.monotonic() - started, 3)
    except subprocess.TimeoutExpired as exc:
        stderr_path.write_text(f"Timed out after {exc.timeout} seconds\n", encoding="utf-8")
        return 124, round(time.monotonic() - started, 3)


def _write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# ACE Turbo vs SFT Comparison",
        "",
        "Same prompt, seed, and duration; only checkpoint and inference steps differ.",
        "",
        f"- Prompt: {report['prompt']}",
        f"- Seed: `{report['seed']}`",
        f"- Duration: `{report['duration_seconds']}s`",
        f"- Final SFT installed: `{report['final_sft_available']}`",
        "",
        "## Variants",
        "",
    ]
    for variant in report["variants"]:
        audio = variant.get("audio") or {}
        lines.extend(
            [
                f"### {variant['label']} (`{variant['id']}`)",
                "",
                f"- Checkpoint: `{variant['checkpoint']}`",
                f"- Steps: `{variant['inference_steps']}`",
                f"- Output: `{variant.get('output_path', '')}`",
                f"- Return code: `{variant.get('returncode')}`",
                f"- Elapsed: `{variant.get('elapsed_seconds')}s`",
                f"- Audio OK: `{audio.get('ok')}`",
                f"- Duration: `{audio.get('duration_seconds')}s`",
                "",
            ]
        )
    lines.extend(["## Summary", ""])
    summary = report["summary"]
    lines.append(f"- All attempted variants succeeded: `{summary['all_succeeded']}`")
    lines.append(f"- All WAVs valid: `{summary['all_audio_valid']}`")
    if summary.get("skipped"):
        lines.append(f"- Skipped: {', '.join(summary['skipped'])}")
    path.write_text("\n".join(lines), encoding="utf-8")


def compare_ace_turbo_vs_sft(
    *,
    prompt: str = DEFAULT_PROMPT,
    lyrics: str = DEFAULT_LYRICS,
    seed: int = DEFAULT_SEED,
    duration_seconds: int = DEFAULT_DURATION,
    offload_to_cpu: bool = True,
    ffprobe: str = "ffprobe",
) -> dict[str, Any]:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()

    checkpoint_dir = settings.ace_model_dir.expanduser().resolve()
    sft_ready = final_sft_installed(checkpoint_dir)
    variants = build_variants(include_sft=sft_ready)
    skipped = [] if sft_ready else [v["id"] for v in SFT_VARIANTS]

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    experiment_dir = settings.data_dir / "experiments" / "ace-turbo-vs-sft" / timestamp
    outputs_dir = experiment_dir / "outputs"
    requests_dir = experiment_dir / "requests"
    logs_dir = experiment_dir / "logs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    requests_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    prompt_file = requests_dir / "prompt.txt"
    lyrics_file = requests_dir / "lyrics.txt"
    _write_text(prompt_file, prompt)
    _write_text(lyrics_file, lyrics)

    env = ace_subprocess_env(settings)
    ace_script = (ROOT / "scripts" / "ace_runner.py").resolve()

    variant_reports: list[dict[str, Any]] = []
    for variant in variants:
        output_path = outputs_dir / f"{variant['id']}.wav"
        stdout_path = logs_dir / f"{variant['id']}.stdout.log"
        stderr_path = logs_dir / f"{variant['id']}.stderr.log"
        command = build_generation_command(
            ace_python=settings.ace_python,
            ace_script=ace_script,
            prompt_file=prompt_file,
            lyrics_file=lyrics_file,
            output_path=output_path,
            model_dir=checkpoint_dir,
            device=settings.ace_device,
            seed=seed,
            duration=duration_seconds,
            checkpoint=variant["checkpoint"],
            inference_steps=variant["inference_steps"],
            offload_to_cpu=offload_to_cpu,
        )
        returncode, elapsed = _run_generation(
            command,
            env=env,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout=settings.ace_timeout_seconds,
        )
        audio = validate_generated_audio(
            output_path,
            ffprobe=ffprobe,
            expected_duration_seconds=duration_seconds,
        )
        profile = None
        if variant["checkpoint"] == FINAL_SFT_CHECKPOINT:
            profile = build_final_sft_profile(inference_steps=variant["inference_steps"]).model_dump()
        variant_reports.append({
            **variant,
            "output_path": str(output_path),
            "stdout_log_path": str(stdout_path),
            "stderr_log_path": str(stderr_path),
            "command": command,
            "returncode": returncode,
            "elapsed_seconds": elapsed,
            "audio": audio,
            "final_sft_profile": profile,
            "success": returncode == 0 and bool(audio["ok"]),
        })

    all_succeeded = all(item["success"] for item in variant_reports)
    all_audio_valid = all(bool(item["audio"]["ok"]) for item in variant_reports)
    report = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "prompt": prompt,
        "lyrics": lyrics,
        "seed": seed,
        "duration_seconds": duration_seconds,
        "final_sft_available": sft_ready,
        "offload_to_cpu": offload_to_cpu,
        "model_dir": str(checkpoint_dir),
        "variants": variant_reports,
        "summary": {
            "variant_count": len(variant_reports),
            "all_succeeded": all_succeeded,
            "all_audio_valid": all_audio_valid,
            "skipped": skipped,
        },
        "success": all_succeeded,
    }
    report_path = experiment_dir / "report.json"
    markdown_path = experiment_dir / "report.md"
    report["report_path"] = str(report_path)
    report["markdown_report_path"] = str(markdown_path)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_markdown_report(report, markdown_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare turbo 8-step vs SFT 24/50-step ACE generation")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--lyrics", default=DEFAULT_LYRICS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION)
    parser.add_argument("--no-offload", action="store_true", help="Disable CPU offload")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = compare_ace_turbo_vs_sft(
        prompt=args.prompt,
        lyrics=args.lyrics,
        seed=args.seed,
        duration_seconds=args.duration,
        offload_to_cpu=not args.no_offload,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("ACE turbo vs SFT comparison")
        print(f"Final SFT installed: {report['final_sft_available']}")
        print(f"Variants run: {report['summary']['variant_count']}")
        if report["summary"]["skipped"]:
            print(f"Skipped (missing SFT): {', '.join(report['summary']['skipped'])}")
        for variant in report["variants"]:
            ok = variant["audio"]["ok"]
            print(
                f"  - {variant['label']}: ok={ok} "
                f"duration={variant['audio'].get('duration_seconds')}s "
                f"elapsed={variant['elapsed_seconds']}s"
            )
        print(f"Report: {report['report_path']}")
        print(f"Markdown: {report['markdown_report_path']}")
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
