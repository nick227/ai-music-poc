#!/usr/bin/env python3
"""
Diagnostic tool for the SVS (Singing Voice Synthesis) stack.

Checks environment configuration, Python interpreter, onnxruntime availability,
and TIGER model directory structure. Optionally runs a smoke render.

Usage:
  python scripts/svs_doctor.py
  python scripts/svs_doctor.py --skip-smoke
  SVS_BACKEND=diffsinger SVS_TIGER_DIR=~/web/diffsinger-env/tiger python scripts/svs_doctor.py
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def _warn(msg: str) -> None:
    print(f" WARN {msg}")


def _fail(msg: str) -> None:
    print(f" FAIL {msg}")


def _header(title: str) -> None:
    print(f"\n── {title} ──")


def check_env(settings) -> list[str]:
    _header("Environment variables")
    issues: list[str] = []

    backend = settings.svs_backend
    _ok(f"SVS_BACKEND = {backend!r}")

    if settings.svs_enabled:
        _ok("SVS_ENABLED = true")
    else:
        _warn("SVS_ENABLED = false — SVS will not run (mock fallback only)")

    _ok(f"SVS_PYTHON = {settings.svs_python}")
    _ok(f"SVS_SCRIPT = {settings.svs_script}")
    _ok(f"SVS_TIMEOUT_SECONDS = {settings.svs_timeout_seconds}")
    _ok(f"SVS_ALLOW_FALLBACK = {settings.svs_allow_fallback}")

    if backend == "diffsinger":
        if settings.svs_tiger_dir:
            _ok(f"SVS_TIGER_DIR = {settings.svs_tiger_dir}")
        else:
            _fail("SVS_TIGER_DIR is not set (required for diffsinger backend)")
            issues.append("SVS_TIGER_DIR missing")
        _ok(f"SVS_SPEAKER = {settings.svs_speaker}")
        if settings.svs_diffsinger_python:
            _ok(f"SVS_DIFFSINGER_PYTHON = {settings.svs_diffsinger_python}")

    return issues


def check_python(settings) -> list[str]:
    _header("Python interpreter")
    issues: list[str] = []
    python = settings.svs_python.expanduser()

    if python.exists():
        result = subprocess.run(
            [str(python), "--version"], capture_output=True, text=True, check=False
        )
        version = (result.stdout + result.stderr).strip()
        _ok(f"{python} → {version}")
    else:
        _fail(f"SVS_PYTHON not found: {python}")
        issues.append(f"SVS_PYTHON not found: {python}")

    return issues


def check_onnxruntime(settings) -> list[str]:
    _header("onnxruntime availability")
    issues: list[str] = []

    if settings.svs_backend != "diffsinger":
        _ok("Backend is not diffsinger — onnxruntime not required")
        return issues

    # Use diffsinger python if specified, otherwise SVS_PYTHON
    ds_python = settings.svs_diffsinger_python or settings.svs_python
    python = ds_python.expanduser()

    if not python.exists():
        _fail(f"Python not found: {python}")
        issues.append(f"Python not found: {python}")
        return issues

    result = subprocess.run(
        [str(python), "-c", "import onnxruntime as ort; print(ort.__version__)"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode == 0:
        version = result.stdout.strip()
        _ok(f"onnxruntime {version} importable")
    else:
        _fail("onnxruntime not importable from SVS_PYTHON env")
        _fail(f"  {result.stderr.strip()[:300]}")
        issues.append("onnxruntime not importable")

    # Check for CUDA provider
    cuda_check = subprocess.run(
        [
            str(python), "-c",
            "import onnxruntime as ort; "
            "providers = ort.get_available_providers(); "
            "print('CUDA' if 'CUDAExecutionProvider' in providers else 'CPU-only')"
        ],
        capture_output=True, text=True, check=False,
    )
    if cuda_check.returncode == 0:
        provider_info = cuda_check.stdout.strip()
        if "CUDA" in provider_info:
            _ok("CUDAExecutionProvider available")
        else:
            _warn("Only CPUExecutionProvider available — TIGER acoustic model requires CUDA")
            issues.append("No CUDA provider — inference will fail on acoustic model")
    return issues


def check_tiger_dir(settings) -> list[str]:
    _header("TIGER model directory")
    issues: list[str] = []

    if settings.svs_backend != "diffsinger":
        _ok("Backend is not diffsinger — TIGER dir not required")
        return issues

    tiger_dir = settings.svs_tiger_dir
    if tiger_dir is None:
        _fail("SVS_TIGER_DIR is not set")
        issues.append("SVS_TIGER_DIR not set")
        return issues

    tiger = tiger_dir.expanduser().resolve()
    if not tiger.exists():
        _fail(f"TIGER directory does not exist: {tiger}")
        issues.append(f"TIGER dir not found: {tiger}")
        return issues

    _ok(f"TIGER dir exists: {tiger}")

    required = {
        "dsacoustic/acoustic.onnx": "acoustic model (327 MB)",
        "dsacoustic/phonemes.txt": "phoneme map",
        "dsvocoder/tgm_hifigan.onnx": "vocoder (56 MB)",
    }
    for rel, desc in required.items():
        path = tiger / rel
        if path.exists():
            size_mb = path.stat().st_size / (1024 * 1024)
            _ok(f"{rel} ({size_mb:.0f} MB) — {desc}")
        else:
            _fail(f"{rel} not found — {desc}")
            issues.append(f"Missing: {rel}")

    # Check for at least one speaker embedding
    speaker = settings.svs_speaker
    emb_path = tiger / "dsacoustic" / f"{speaker}.emb"
    if emb_path.exists():
        _ok(f"Speaker embedding: {speaker}.emb")
    else:
        _warn(f"Speaker embedding not found: dsacoustic/{speaker}.emb")
        # List available speakers
        embs = list((tiger / "dsacoustic").glob("*.emb"))
        if embs:
            names = [e.stem for e in embs]
            _warn(f"  Available speakers: {', '.join(names)}")
            issues.append(f"Speaker {speaker!r} not found; available: {', '.join(names)}")
        else:
            _fail("No .emb speaker files found in dsacoustic/")
            issues.append("No speaker embeddings found")

    return issues


def check_svs_script(settings) -> list[str]:
    _header("SVS runner script")
    issues: list[str] = []

    script = settings.svs_script.expanduser()
    if script.exists():
        _ok(f"Script exists: {script}")
    else:
        _fail(f"SVS_SCRIPT not found: {script}")
        issues.append(f"SVS_SCRIPT not found: {script}")

    return issues


def smoke_render(settings) -> list[str]:
    _header("Smoke render")
    issues: list[str] = []

    backend = settings.svs_backend
    _ok(f"Running mock smoke render (backend=mock, bypasses {backend!r})")

    # Use a minimal test score for the smoke test
    test_score = {
        "version": 1,
        "bpm": 120,
        "duration_beats": 4.0,
        "events": [
            {
                "type": "note",
                "syllable_text": "hel",
                "phonemes": ["HH", "EH", "L"],
                "midi": 60,
                "note_name": "C4",
                "start_beats": 0.0,
                "duration_beats": 1.0,
                "phrase_end": False,
            },
            {
                "type": "note",
                "syllable_text": "lo",
                "phonemes": ["OW"],
                "midi": 62,
                "note_name": "D4",
                "start_beats": 1.0,
                "duration_beats": 1.0,
                "phrase_end": True,
            },
            {"type": "rest", "start_beats": 2.0, "duration_beats": 2.0},
        ],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        score_path = Path(tmpdir) / "smoke_score.json"
        output_path = Path(tmpdir) / "smoke_out.wav"
        report_path = Path(tmpdir) / "smoke_report.json"

        score_path.write_text(json.dumps(test_score), encoding="utf-8")

        python = settings.svs_python.expanduser()
        script = settings.svs_script.expanduser()

        cmd = [
            str(python), str(script),
            "--score", str(score_path),
            "--output", str(output_path),
            "--backend", "mock",
            "--report", str(report_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)

        if result.returncode == 0 and output_path.exists():
            size = output_path.stat().st_size
            _ok(f"Smoke render OK — {size} bytes at {output_path.name}")
            if report_path.exists():
                rep = json.loads(report_path.read_text())
                _ok(f"  Report: backend={rep.get('backend')}, ok={rep.get('ok')}")
        else:
            _fail("Smoke render failed")
            if result.stderr:
                _fail(f"  stderr: {result.stderr.strip()[:400]}")
            if result.stdout:
                _fail(f"  stdout: {result.stdout.strip()[:400]}")
            issues.append("Smoke render failed")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-smoke", action="store_true", help="Skip the smoke render test")
    args = parser.parse_args()

    from app.core.config import Settings
    settings = Settings()

    print("SVS Doctor")
    print(f"  Backend: {settings.svs_backend}")
    print(f"  Enabled: {settings.svs_enabled}")

    all_issues: list[str] = []
    all_issues += check_env(settings)
    all_issues += check_python(settings)
    all_issues += check_svs_script(settings)

    if settings.svs_backend == "diffsinger":
        all_issues += check_onnxruntime(settings)
        all_issues += check_tiger_dir(settings)

    if not args.skip_smoke:
        all_issues += smoke_render(settings)

    _header("Summary")
    if all_issues:
        print(f"\n  {len(all_issues)} issue(s) found:")
        for issue in all_issues:
            print(f"    - {issue}")
        return 1
    else:
        print("\n  All checks passed.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
