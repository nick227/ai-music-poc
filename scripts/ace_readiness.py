#!/usr/bin/env python3
"""
ACE runtime readiness check — code-first, no Gradio.

Detects local hardware and dependencies, selects conservative defaults,
runs a generation smoke test, validates the output with ffprobe, and
persists results to data/ace_hardware_profile.json.

Exit codes:
  0  All gates passed — ACE is usable
  1  One or more gates failed
  2  Configuration error (missing paths etc.)

Usage:
  python scripts/ace_readiness.py               # full check + smoke test
  python scripts/ace_readiness.py --no-generate # hardware + deps only, skip generation
  python scripts/ace_readiness.py --keep-output # preserve the smoke-test WAV
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from app.core.ace_runtime import (
    build_runtime_status,
    run_smoke_test,
    save_runtime_profile,
)
from app.core.config import get_settings
from app.core.hardware import build_hardware_profile
from app.generators.ace_step.env import ace_subprocess_env
from app.generators.ace_step.health import check_ace_packages


def _banner(title: str) -> None:
    print(f"\n== {title} ==")


def main() -> int:
    parser = argparse.ArgumentParser(description="ACE runtime readiness check")
    parser.add_argument("--no-generate", action="store_true", help="Skip smoke-test generation")
    parser.add_argument("--keep-output", action="store_true", help="Preserve smoke-test WAV in data/model_outputs/")
    parser.add_argument("--duration", type=int, default=10, help="Smoke test duration in seconds (default: 10)")
    parser.add_argument("--no-persist", action="store_true", help="Skip writing data/ace_hardware_profile.json")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()

    # ------------------------------------------------------------------ #
    # 1. Hardware detection
    # ------------------------------------------------------------------ #
    _banner("Hardware detection")
    checkpoint_dir = settings.ace_model_dir.expanduser()
    hw = build_hardware_profile(
        checkpoint_dir=checkpoint_dir,
        ace_python=settings.ace_python,
        ace_env=ace_subprocess_env(settings),
    )
    print(f"GPU:        {hw.gpu_name or '(none)'} — {hw.gpu_vram_mb} MiB VRAM")
    print(f"CUDA:       {'yes' if hw.cuda_available else 'NO'} (version: {hw.cuda_version or 'unknown'})")
    print(f"ffmpeg:     {hw.ffmpeg_path or 'NOT FOUND'}")
    print(f"ffprobe:    {hw.ffprobe_path or 'NOT FOUND'}")
    print(f"Model dir:  {hw.checkpoint_dir} (exists={hw.checkpoint_dir_exists})")
    print(f"Turbo ckpt: {hw.turbo_checkpoint or 'NOT FOUND'}")
    print(f"XL SFT:     {'ready' if hw.xl_sft_available else 'NOT FOUND (optional top model)'}")
    print(f"XL Turbo:   {'ready' if hw.xl_turbo_available else 'NOT FOUND (optional)'}")
    print(f"LM safe (0.6B): {hw.lm_safe_checkpoint or 'NOT FOUND'}")
    print(f"LM avail:   {hw.lm_checkpoint or 'none'}")
    print(f"VAE:        {'yes' if hw.vae_present else 'NOT FOUND'}")
    safe = hw.safe_recommended_config
    detected = hw.detected_available_config
    if safe:
        print(f"\nSafe recommended config:    {safe.description}")
        print(f"  checkpoint={safe.checkpoint}, lm={safe.lm_model or 'none'}, "
              f"steps={safe.inference_steps}, batch={safe.batch_size}, "
              f"offload={safe.offload_to_cpu}, device={safe.device}")
    if detected and detected != safe:
        print(f"\nDetected available config:  {detected.description}")
        print(f"  checkpoint={detected.checkpoint}, lm={detected.lm_model or 'none'}, "
              f"steps={detected.inference_steps}, batch={detected.batch_size}, "
              f"offload={detected.offload_to_cpu}, device={detected.device}")
    if hw.experimental_config_options:
        print(f"\nExperimental options ({len(hw.experimental_config_options)}):")
        for exp in hw.experimental_config_options:
            print(f"  - {exp.description}")
    if hw.final_render_profiles:
        print(f"\nFinal-render profiles ({len(hw.final_render_profiles)}):")
        for profile in hw.final_render_profiles:
            print(
                f"  - {profile.name}: checkpoint={profile.checkpoint}, "
                f"steps={profile.inference_steps}, lm={profile.lm_model or 'none'}, "
                f"offload={profile.offload_to_cpu}"
            )

    # ------------------------------------------------------------------ #
    # 2. Package check
    # ------------------------------------------------------------------ #
    _banner("Package check (ACE venv)")
    packages = check_ace_packages(settings)
    packages_ok = bool(packages.get("ok")) and not packages.get("missing_packages")
    pkgs = packages.get("packages") or {}
    for name, ver in pkgs.items():
        status_str = "ok" if not str(ver).startswith("missing:") else f"MISSING ({ver})"
        print(f"  {name}: {status_str}")
    if packages.get("missing_packages"):
        print(f"  Missing: {packages['missing_packages']}")
    print(f"Packages: {'OK' if packages_ok else 'FAIL'}")

    # ------------------------------------------------------------------ #
    # 3. Smoke test
    # ------------------------------------------------------------------ #
    smoke = None
    if args.no_generate:
        print("\n[--no-generate] Skipping smoke test.")
    elif not packages_ok:
        print("\nSkipping smoke test — packages not ready.")
    elif not hw.cuda_available:
        print("\nSkipping smoke test — CUDA not available.")
    elif not hw.checkpoint_dir_exists or not hw.turbo_checkpoint:
        print("\nSkipping smoke test — turbo checkpoint not found.")
    else:
        _banner("Smoke test (automated generation)")
        kept_output = (ROOT / "data" / "model_outputs" / "ace-smoke-test.wav") if args.keep_output else None
        ffprobe = hw.ffprobe_path or "ffprobe"
        safe_dur = (hw.safe_recommended_config.duration if hw.safe_recommended_config else args.duration)
        dur_used = args.duration if args.duration != 10 else safe_dur
        print(f"Running {dur_used}s generation via {settings.ace_script} ...")
        smoke = run_smoke_test(
            ace_python=settings.ace_python,
            ace_script=settings.ace_script,
            ace_model_dir=settings.ace_model_dir.expanduser(),
            ace_device=settings.ace_device,
            ace_env=ace_subprocess_env(settings),
            timeout_seconds=settings.ace_timeout_seconds,
            duration=dur_used,
            ffprobe=ffprobe,
            kept_output=kept_output,
        )
        _banner("Smoke test result")
        print(f"ok:           {smoke.ok}")
        print(f"returncode:   {smoke.returncode}")
        if smoke.error:
            print(f"error:        {smoke.error}")
        if smoke.audio:
            a = smoke.audio
            print(f"audio ok:     {a.ok}")
            print(f"  path:       {a.path}")
            print(f"  size:       {a.file_size_bytes} bytes")
            print(f"  duration:   {a.duration_seconds}s")
            print(f"  codec:      {a.codec_name} @ {a.sample_rate}Hz {a.channels}ch")
            if not a.ok:
                print(f"  error:      {a.error}")
        if smoke.stdout_tail:
            print(f"\n-- stdout (tail) --\n{smoke.stdout_tail[-1000:]}")
        if smoke.stderr_tail:
            print(f"\n-- stderr (tail) --\n{smoke.stderr_tail[-500:]}")

    # ------------------------------------------------------------------ #
    # 4. Assemble and persist status
    # ------------------------------------------------------------------ #
    status = build_runtime_status(hw, packages_ok=packages_ok, last_smoke_test=smoke)

    if not args.no_persist:
        profile_path = save_runtime_profile(settings.data_dir, status)
        try:
            rel = profile_path.relative_to(ROOT)
        except ValueError:
            rel = profile_path
        print(f"\nProfile saved to {rel}")

    _banner("Final verdict")
    print(f"ace_usable:   {status.ace_usable}")
    print(f"deps_ok:      {status.deps_ok}")
    print(f"cuda_ok:      {status.cuda_ok}")
    print(f"ffprobe_ok:   {status.ffprobe_ok}")
    print(f"checkpoints:  {status.checkpoints_ok}")
    print(f"generation:   {status.generation_ok}")
    print(f"audio_valid:  {status.audio_valid}")
    print(f"message:      {status.user_message}")
    if status.lm_warning:
        print(f"lm_warning:   {status.lm_warning}")
    if status.final_render_warning:
        print(f"final_render: {status.final_render_warning}")

    return 0 if status.ace_usable else 1


if __name__ == "__main__":
    raise SystemExit(main())
