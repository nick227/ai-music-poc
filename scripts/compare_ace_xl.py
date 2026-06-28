#!/usr/bin/env python3
"""Compare 2B turbo vs XL turbo/SFT ACE generation on identical inputs."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
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

from app.core.ace_profiles import (
    SAFE_TURBO_CHECKPOINT,
    XL_SFT_CHECKPOINT,
    XL_TURBO_CHECKPOINT,
    xl_sft_installed,
    xl_turbo_installed,
)
from app.core.ace_runtime import validate_with_ffprobe
from app.core.audio_validation import validate_wav_output
from app.core.config import get_settings
from app.generators.ace_step.env import ace_subprocess_env

DEFAULT_PROMPT = "ambient ocean waves, soft pads, gentle rhythm, cinematic"
DEFAULT_LYRICS = "[Instrumental]"
DEFAULT_SEED = 4242
DEFAULT_DURATION = 30

TURBO_8 = {
    "id": "turbo_8",
    "label": "2B turbo 8 steps",
    "checkpoint": SAFE_TURBO_CHECKPOINT,
    "inference_steps": 8,
}
XL_TURBO_8 = {
    "id": "xl_turbo_8",
    "label": "XL turbo 8 steps",
    "checkpoint": XL_TURBO_CHECKPOINT,
    "inference_steps": 8,
}
XL_SFT_24 = {
    "id": "xl_sft_24",
    "label": "XL SFT 24 steps",
    "checkpoint": XL_SFT_CHECKPOINT,
    "inference_steps": 24,
}
XL_SFT_50 = {
    "id": "xl_sft_50",
    "label": "XL SFT 50 steps",
    "checkpoint": XL_SFT_CHECKPOINT,
    "inference_steps": 50,
}


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_variants(
    *,
    xl_sft_ready: bool,
    xl_turbo_ready: bool,
    include_xl_sft: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    variants: list[dict[str, Any]] = [TURBO_8]
    skipped: list[str] = []
    if xl_turbo_ready:
        variants.append(XL_TURBO_8)
    else:
        skipped.append(XL_TURBO_8["id"])
    if include_xl_sft and xl_sft_ready:
        variants.extend([XL_SFT_24, XL_SFT_50])
    else:
        if xl_sft_ready and not include_xl_sft:
            skipped.extend([XL_SFT_24["id"], XL_SFT_50["id"]])
        elif not xl_sft_ready:
            skipped.extend([XL_SFT_24["id"], XL_SFT_50["id"]])
    return variants, skipped


def query_gpu_vram_mb() -> int | None:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        result = subprocess.run(
            [smi, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip().splitlines()[0].strip())
    except Exception:
        pass
    return None


class _VramSampler:
    def __init__(self) -> None:
        self._peak_mb = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        def _loop() -> None:
            while not self._stop.is_set():
                used = query_gpu_vram_mb()
                if used is not None and used > self._peak_mb:
                    self._peak_mb = used
                self._stop.wait(0.5)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> int | None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        return self._peak_mb or None


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
    label: str = "",
) -> tuple[int, float, int | None]:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    sampler = _VramSampler()
    sampler.start()
    started = time.monotonic()
    last_heartbeat = 0.0
    print(f"\n>> {label or 'generation'}: starting", flush=True)
    print(f"   logs: {stdout_path.parent}", flush=True)
    try:
        with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
            proc = subprocess.Popen(
                command,
                cwd=str(ROOT),
                env=env,
                stdout=stdout,
                stderr=stderr,
                text=True,
            )
            while proc.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed > timeout:
                    proc.kill()
                    proc.wait(timeout=10)
                    peak_vram_mb = sampler.stop()
                    stderr_path.write_text(
                        stderr_path.read_text(encoding="utf-8") + f"\nTimed out after {timeout} seconds\n",
                        encoding="utf-8",
                    )
                    print(f"   timed out after {timeout}s", flush=True)
                    return 124, round(elapsed, 3), peak_vram_mb
                if elapsed - last_heartbeat >= 15:
                    print(f"   ... still running ({int(elapsed)}s)", flush=True)
                    last_heartbeat = elapsed
                time.sleep(1)
            returncode = proc.returncode or 0
        peak_vram_mb = sampler.stop()
        elapsed = round(time.monotonic() - started, 3)
        print(f"   finished in {elapsed}s (exit {returncode})", flush=True)
        return returncode, elapsed, peak_vram_mb
    except Exception as exc:
        peak_vram_mb = sampler.stop()
        stderr_path.write_text(f"{exc}\n", encoding="utf-8")
        return 1, round(time.monotonic() - started, 3), peak_vram_mb


def _write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# ACE XL Comparison",
        "",
        "Same prompt, seed, and duration; checkpoint and steps vary per variant.",
        "Quality must be judged by listening — this report only validates generation succeeded.",
        "",
        f"- Prompt: {report['prompt']}",
        f"- Seed: `{report['seed']}`",
        f"- Duration: `{report['duration_seconds']}s`",
        f"- XL SFT installed: `{report['xl_sft_available']}`",
        f"- XL Turbo installed: `{report['xl_turbo_available']}`",
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
                f"- Render time: `{variant.get('elapsed_seconds')}s`",
                f"- Peak VRAM: `{variant.get('peak_vram_mb', 'n/a')} MiB`",
                f"- ffprobe OK: `{audio.get('ok')}`",
                f"- Duration: `{audio.get('duration_seconds')}s`",
                f"- RMS: `{audio.get('rms')}`",
                f"- Peak sample: `{audio.get('peak_abs_sample')}`",
                "",
            ]
        )
    lines.extend(["## Summary", ""])
    summary = report["summary"]
    lines.append(f"- All attempted variants succeeded: `{summary['all_succeeded']}`")
    lines.append(f"- All WAVs valid: `{summary['all_audio_valid']}`")
    if summary.get("skipped"):
        lines.append(f"- Skipped (not installed): {', '.join(summary['skipped'])}")
    path.write_text("\n".join(lines), encoding="utf-8")


def compare_ace_xl(
    *,
    prompt: str = DEFAULT_PROMPT,
    lyrics: str = DEFAULT_LYRICS,
    seed: int = DEFAULT_SEED,
    duration_seconds: int = DEFAULT_DURATION,
    offload_to_cpu: bool = True,
    ffprobe: str = "ffprobe",
    include_xl_sft: bool = False,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()

    checkpoint_dir = settings.ace_model_dir.expanduser().resolve()
    xl_sft_ready = xl_sft_installed(checkpoint_dir)
    xl_turbo_ready = xl_turbo_installed(checkpoint_dir)
    variants, skipped = build_variants(
        xl_sft_ready=xl_sft_ready,
        xl_turbo_ready=xl_turbo_ready,
        include_xl_sft=include_xl_sft,
    )
    run_timeout = timeout_seconds if timeout_seconds is not None else settings.ace_timeout_seconds

    print(f"ACE XL comparison — {len(variants)} variant(s), duration={duration_seconds}s, seed={seed}")
    if skipped:
        print(f"Skipped: {', '.join(skipped)}")
    if xl_sft_ready and not include_xl_sft:
        print("XL SFT omitted by default (failed listening on 12GB). Pass --include-xl-sft to benchmark it.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    experiment_dir = settings.data_dir / "experiments" / "ace-xl-comparison" / timestamp
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
    for index, variant in enumerate(variants, start=1):
        output_path = outputs_dir / f"{variant['id']}.wav"
        stdout_path = logs_dir / f"{variant['id']}.stdout.log"
        stderr_path = logs_dir / f"{variant['id']}.stderr.log"
        note = ""
        if variant["checkpoint"] == XL_SFT_CHECKPOINT:
            note = " — loads ~19GB sharded XL model; first run can take 10–20+ min on 12GB"
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
        returncode, elapsed, peak_vram_mb = _run_generation(
            command,
            env=env,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            timeout=run_timeout,
            label=f"[{index}/{len(variants)}] {variant['label']}{note}",
        )
        audio = validate_generated_audio(
            output_path,
            ffprobe=ffprobe,
            expected_duration_seconds=duration_seconds,
        )
        variant_reports.append({
            **variant,
            "output_path": str(output_path),
            "stdout_log_path": str(stdout_path),
            "stderr_log_path": str(stderr_path),
            "command": command,
            "returncode": returncode,
            "elapsed_seconds": elapsed,
            "peak_vram_mb": peak_vram_mb,
            "audio": audio,
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
        "xl_sft_available": xl_sft_ready,
        "xl_turbo_available": xl_turbo_ready,
        "offload_to_cpu": offload_to_cpu,
        "include_xl_sft": include_xl_sft,
        "timeout_seconds": run_timeout,
        "model_dir": str(checkpoint_dir),
        "quality_note": "Subjective quality must be judged by listening. XL SFT disabled for app generation (failed listening on 12GB).",
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
    parser = argparse.ArgumentParser(description="Compare 2B turbo vs XL turbo/SFT ACE generation")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--lyrics", default=DEFAULT_LYRICS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION)
    parser.add_argument("--no-offload", action="store_true", help="Disable CPU offload")
    parser.add_argument(
        "--include-xl-sft",
        action="store_true",
        help="Include XL SFT 24/50 variants (slow ~19GB load each; known noisy on 12GB)",
    )
    parser.add_argument("--timeout", type=int, default=None, help="Per-variant timeout seconds (default: ACE_TIMEOUT_SECONDS)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = compare_ace_xl(
        prompt=args.prompt,
        lyrics=args.lyrics,
        seed=args.seed,
        duration_seconds=args.duration,
        offload_to_cpu=not args.no_offload,
        include_xl_sft=args.include_xl_sft,
        timeout_seconds=args.timeout,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("ACE XL comparison")
        print(f"XL SFT installed: {report['xl_sft_available']}")
        print(f"XL Turbo installed: {report['xl_turbo_available']}")
        print(f"Variants run: {report['summary']['variant_count']}")
        if report["summary"]["skipped"]:
            print(f"Skipped: {', '.join(report['summary']['skipped'])}")
        for variant in report["variants"]:
            ok = variant["audio"]["ok"]
            print(
                f"  - {variant['label']}: ok={ok} "
                f"duration={variant['audio'].get('duration_seconds')}s "
                f"elapsed={variant['elapsed_seconds']}s "
                f"peak_vram={variant.get('peak_vram_mb')}MiB"
            )
        print(f"Report: {report['report_path']}")
        print(f"Markdown: {report['markdown_report_path']}")
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
