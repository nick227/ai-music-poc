#!/usr/bin/env python3
"""Synthetic Dark Bell v1 — LoRA Strength Sweep.

For each of the 3 comparison prompts × 3 seeds, generates five clips:
  - strength 0.00  (base model, no LoRA)
  - strength 0.25
  - strength 0.50
  - strength 0.75
  - strength 1.00

Total: 45 clips.  Each WAV is validated with ffprobe; RMS, peak, ZCR, spectral
centroid, spectral rolloff, and band energy ratios (low/mid/presence/air) are
collected.  Results are written as report.json and report.md (with a blank manual
listening checklist and a metric-delta summary table) under
data/experiments/synthetic-dark-bell-lora-strength-sweep/<ts>/.

DISCLAIMER
----------
Outputs demonstrate LoRA influence relative to the base model.
This does NOT prove automatic quality improvement.

GATE: set SYNTH_LORA_STRENGTH_SWEEP=1 or pass --run to generate clips.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import subprocess
import sys
import wave as _wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional  # noqa: F401 – Optional needed by StyleVersion Pydantic forward refs

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

from app.core.config import get_settings
from app.domain.models import GenerationRequest
from app.generators.ace_step.command_builder import AceCommandBuilder
from app.services.style_version_service import StyleVersionService
from app.storage.style_version_store import StyleVersionStore
from app.storage.training_run_store import TrainingRunStore
from app.training.ace_subprocess_env import ace_training_env
from app.training.ace_train_commands import LORA_CONFIG_NAME, LORA_WEIGHTS_NAME

from app.domain.style_versions import StyleVersion  # noqa: F401 – needed for model_rebuild
from scripts.verify_synthetic_lora_training_flow import (
    COMPARISON_DISCLAIMER,
    COMPARISON_DURATION_SECONDS,
    COMPARISON_PROMPTS,
    COMPARISON_SEEDS,
)

# Resolve Optional forward references in StyleVersion so model_validate_json works.
StyleVersion.model_rebuild()

# ── Constants ──────────────────────────────────────────────────────────────────

GATE_ENV = "SYNTH_LORA_STRENGTH_SWEEP"

MODEL_VERSION_ID  = "style_287ee3366b5a4df0824a9c923e9a1de8"
TRAINING_RUN_ID   = "train_fc17ee80baf24b12aad50679a9e8df84"
BASE_MODEL_NAME   = "ACE-Step v1.5 Turbo"

SWEEP_STRENGTHS: list[float] = [0.0, 0.25, 0.50, 0.75, 1.00]
SWEEP_PROMPTS     = COMPARISON_PROMPTS
SWEEP_SEEDS       = COMPARISON_SEEDS
SWEEP_DURATION    = COMPARISON_DURATION_SECONDS
SWEEP_DISCLAIMER  = COMPARISON_DISCLAIMER


# ── Gate helpers ───────────────────────────────────────────────────────────────

def is_sweep_enabled(flag: bool = False) -> bool:
    return flag or os.environ.get(GATE_ENV, "").strip() == "1"


# ── Lineage validation ─────────────────────────────────────────────────────────

def validate_sweep_lineage(
    model_version,
    training_run,
    *,
    expected_training_run_id: str,
) -> tuple[bool, list[str]]:
    """Verify Model Version → TrainingRun link and Studio artifact type."""
    failures: list[str] = []
    if model_version.training_run_id != expected_training_run_id:
        failures.append(
            f"model_version.training_run_id {model_version.training_run_id!r} != "
            f"expected {expected_training_run_id!r}"
        )
    if model_version.artifact_type != "lora":
        failures.append(
            f"model_version.artifact_type {model_version.artifact_type!r} != 'lora'"
        )
    if training_run.artifact_type != "lora":
        failures.append(
            f"training_run.artifact_type {training_run.artifact_type!r} != 'lora'"
        )
    return (len(failures) == 0), failures


# ── LoRA file validation ───────────────────────────────────────────────────────

def validate_lora_files(lora_dir: Path) -> dict[str, Any]:
    """Check Studio LoRA file names exist and have nonzero size."""
    results: dict[str, Any] = {}
    for name in (LORA_WEIGHTS_NAME, LORA_CONFIG_NAME):
        path = lora_dir / name
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
        results[name] = {"exists": exists, "size_bytes": size, "nonzero": size > 0}
    all_ok = all(v["exists"] and v["nonzero"] for v in results.values())
    return {"files": results, "ok": all_ok, "lora_dir": str(lora_dir)}


# ── Sweep group planning ───────────────────────────────────────────────────────

def plan_sweep_groups(
    experiment_dir: Path,
    lora_load_path: str | None,
    *,
    lora_available: bool = False,
) -> list[dict[str, Any]]:
    """Return 9 groups × 5 strength levels = 45 generation points (pure function).

    No generation is attempted.  Each point has:
      strength, use_lora, lora_path, lora_scale, output, generation_status, stats
    """
    groups: list[dict[str, Any]] = []
    for pi, prompt in enumerate(SWEEP_PROMPTS):
        for si, seed in enumerate(SWEEP_SEEDS):
            group_id = f"group_p{pi}_s{si}"
            points: list[dict[str, Any]] = []
            for strength in SWEEP_STRENGTHS:
                use_lora = (strength > 0.0) and lora_available
                filename = f"{group_id}_str{strength:.2f}.wav"
                points.append({
                    "strength": strength,
                    "use_lora": use_lora,
                    "lora_path": lora_load_path if use_lora else None,
                    "lora_scale": strength,
                    "output": str(experiment_dir / filename),
                    "generation_status": "planned",
                    "stats": None,
                })
            groups.append({
                "group_id": group_id,
                "prompt_index": pi,
                "seed_index": si,
                "prompt": prompt,
                "seed": seed,
                "duration_seconds": SWEEP_DURATION,
                "points": points,
            })
    return groups


# ── WAV / ffprobe validation ───────────────────────────────────────────────────

def _ffprobe_wav(path: Path) -> dict[str, Any] | None:
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=10)
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {}
        )
        return {
            "duration_seconds": round(float(fmt.get("duration") or stream.get("duration") or 0), 3),
            "size_bytes": int(fmt.get("size") or 0),
            "sample_rate": int(stream.get("sample_rate") or 0),
            "channels": int(stream.get("channels") or 0),
            "codec": stream.get("codec_name", ""),
        }
    except Exception:
        return None


def _wav_rms_peak(path: Path) -> dict[str, float]:
    try:
        with _wave.open(str(path), "rb") as wf:
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
        n_samples = len(raw) // 2
        values = struct.unpack(f"<{n_samples}h", raw)
        peak = max(abs(v) for v in values) / 32767.0 if values else 0.0
        rms_raw = math.sqrt(sum(v * v for v in values) / len(values)) if values else 0.0
        return {"rms": round(rms_raw / 32767.0, 6), "peak": round(peak, 6)}
    except Exception:
        return {"rms": 0.0, "peak": 0.0}


def _wav_zcr(path: Path) -> float:
    """Zero-crossing rate — proxy for high-frequency energy (higher = more shimmer)."""
    try:
        with _wave.open(str(path), "rb") as wf:
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
        n_samples = len(raw) // 2
        if n_samples < 2:
            return 0.0
        values = struct.unpack(f"<{n_samples}h", raw)
        crossings = sum(
            1 for i in range(1, len(values))
            if (values[i] >= 0) != (values[i - 1] >= 0)
        )
        return round(crossings / (len(values) - 1), 6)
    except Exception:
        return 0.0


# Band boundaries (Hz) — low / mid / presence / air-shimmer
_BANDS = [("low", 20.0, 250.0), ("mid", 250.0, 2000.0),
          ("presence", 2000.0, 6000.0), ("air", 6000.0, 14000.0)]

_SPECTRAL_ZERO: dict[str, Any] = {
    "spectral_centroid": 0.0, "spectral_rolloff": 0.0,
    "low_ratio": 0.0, "mid_ratio": 0.0,
    "presence_ratio": 0.0, "air_ratio": 0.0, "presence_plus_air": 0.0,
}


def _wav_spectral_stats(path: Path) -> dict[str, Any]:
    """Spectral centroid, rolloff (85%), and band energy ratios via numpy FFT.

    Bands: low 20-250 Hz, mid 250-2000 Hz, presence 2000-6000 Hz, air 6000-14000 Hz.
    Returns _SPECTRAL_ZERO if numpy is unavailable or the file cannot be read.
    """
    try:
        import numpy as np
    except ImportError:
        return dict(_SPECTRAL_ZERO)
    try:
        with _wave.open(str(path), "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
        if sample_width != 2 or n_frames < 2:
            return dict(_SPECTRAL_ZERO)
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32767.0
        if n_channels == 2:
            samples = (samples[::2] + samples[1::2]) * 0.5  # stereo → mono mix
        spectrum = np.abs(np.fft.rfft(samples))
        freqs = np.fft.rfftfreq(len(samples), d=1.0 / sample_rate)
        power = spectrum ** 2
        total_power = float(power.sum())
        if total_power == 0.0:
            return dict(_SPECTRAL_ZERO)
        total_mag = float(spectrum.sum())
        centroid = float((freqs * spectrum).sum() / total_mag) if total_mag > 0.0 else 0.0
        cumsum = np.cumsum(power)
        rolloff_idx = int(np.searchsorted(cumsum, 0.85 * total_power))
        rolloff = float(freqs[min(rolloff_idx, len(freqs) - 1)])
        ratios: dict[str, float] = {}
        for name, f_lo, f_hi in _BANDS:
            mask = (freqs >= f_lo) & (freqs < f_hi)
            ratios[f"{name}_ratio"] = round(float(power[mask].sum() / total_power), 6)
        return {
            "spectral_centroid": round(centroid, 2),
            "spectral_rolloff": round(rolloff, 2),
            **ratios,
            "presence_plus_air": round(ratios["presence_ratio"] + ratios["air_ratio"], 6),
        }
    except Exception:
        return dict(_SPECTRAL_ZERO)


def validate_sweep_wav(path: Path) -> dict[str, Any]:
    """ffprobe + RMS + peak + ZCR + spectral metrics."""
    exists = path.is_file()
    if not exists:
        return {"path": str(path), "exists": False, "valid": False,
                "ffprobe": None, "rms": 0.0, "peak": 0.0, "zcr": 0.0,
                **_SPECTRAL_ZERO}
    ffprobe = _ffprobe_wav(path)
    amp = _wav_rms_peak(path)
    zcr = _wav_zcr(path)
    spectral = _wav_spectral_stats(path)
    valid = ffprobe is not None and ffprobe.get("duration_seconds", 0) > 0
    return {"path": str(path), "exists": True, "valid": valid,
            "ffprobe": ffprobe, "zcr": zcr, **amp, **spectral}


# ── Generation ─────────────────────────────────────────────────────────────────

def _ace_command_configured(settings) -> bool:
    return bool(settings.ace_command_template.strip()) and settings.ace_enabled


def _attempt_point(
    group: dict[str, Any],
    point: dict[str, Any],
    settings,
    ace_step_dir: Path,
) -> dict[str, Any]:
    result = dict(point)
    output_path = Path(point["output"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        builder = AceCommandBuilder(settings)
        req = GenerationRequest(
            title=f"Sweep {group['group_id']} str{point['strength']:.2f}",
            prompt=group["prompt"],
            mode="instrumental",
            duration_seconds=group["duration_seconds"],
            seed=group["seed"],
            lora_path=point["lora_path"],
            lora_scale=point["lora_scale"],
        )
        command = builder.build(req, output_path)
        env = ace_training_env(ace_step_dir=ace_step_dir)
        proc = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=120, env=env
        )
        if proc.returncode == 0 and output_path.is_file():
            result["stats"] = validate_sweep_wav(output_path)
            result["generation_status"] = "succeeded"
        else:
            result["generation_status"] = "failed"
            result["generation_error"] = (proc.stderr or proc.stdout or "")[:400]
    except subprocess.TimeoutExpired:
        result["generation_status"] = "timeout"
    except Exception as exc:
        result["generation_status"] = "error"
        result["generation_error"] = str(exc)[:400]
    return result


def run_sweep(
    groups: list[dict[str, Any]],
    settings,
    *,
    mandatory: bool = False,
) -> list[dict[str, Any]]:
    """Attempt all 45 generation points.

    When mandatory=True, raises RuntimeError if ACE is not configured or paths
    are missing rather than silently leaving points as planned/skipped.
    """
    if not _ace_command_configured(settings):
        if mandatory:
            raise RuntimeError(
                "Mandatory sweep requires ACE to be configured "
                "(ACE_ENABLED=true and ace_command_template set). "
                "Pass --allow-planned-sweep to skip."
            )
        return [
            dict(g, points=[dict(p, generation_status="skipped_ace_not_configured")
                            for p in g["points"]])
            for g in groups
        ]

    ace_step_dir = settings.ace_step_dir
    if ace_step_dir is None or not ace_step_dir.is_dir():
        if mandatory:
            raise RuntimeError(
                "Mandatory sweep requires ACE_STEP_DIR to be a valid directory. "
                "Pass --allow-planned-sweep to skip."
            )
        return [
            dict(g, points=[dict(p, generation_status="skipped_ace_step_dir_missing")
                            for p in g["points"]])
            for g in groups
        ]
    ace_step_dir = ace_step_dir.expanduser().resolve()

    updated: list[dict[str, Any]] = []
    for group in groups:
        updated_points = [
            _attempt_point(group, point, settings, ace_step_dir)
            for point in group["points"]
        ]
        updated.append(dict(group, points=updated_points))
    return updated


# ── Report markdown ────────────────────────────────────────────────────────────

def _strength_means(
    groups: list[dict[str, Any]], strengths: list[float]
) -> dict[float, dict[str, Any]]:
    """Compute per-strength means of valid-clip metrics across all groups."""
    buckets: dict[float, list[dict[str, Any]]] = {s: [] for s in strengths}
    for g in groups:
        for pt in g["points"]:
            st = pt.get("stats") or {}
            if st.get("valid"):
                buckets[pt["strength"]].append(st)
    result: dict[float, dict[str, Any]] = {}
    for s in strengths:
        pts = buckets[s]
        n = len(pts)
        if n == 0:
            result[s] = {"n": 0}
        else:
            result[s] = {
                "n": n,
                "rms": sum(p.get("rms", 0.0) for p in pts) / n,
                "zcr": sum(p.get("zcr", 0.0) for p in pts) / n,
                "centroid": sum(p.get("spectral_centroid", 0.0) for p in pts) / n,
                "air": sum(p.get("air_ratio", 0.0) for p in pts) / n,
                "presence_plus_air": sum(p.get("presence_plus_air", 0.0) for p in pts) / n,
            }
    return result


def write_report_md(report: dict[str, Any], path: Path) -> None:
    mv = report["model_version"]
    strengths: list[float] = report["sweep_strengths"]
    lines: list[str] = []

    lines += [
        "# Synthetic Dark Bell v1 — LoRA Strength Sweep",
        "",
        f"**Model Version:** {mv['id']}  ",
        f"**Base Model:** {mv['base_model_name']}  ",
        f"**Training Run:** {report['training_run_id']}  ",
        f"**Date:** {report['verified_at'][:10]}  ",
        f"**Strengths:** {', '.join(f'{s:.2f}' + (' (base)' if s == 0.0 else '') for s in strengths)}  ",
        f"**Total clips:** {report['total_points']} "
        f"({report['generated_count']} generated, {report['valid_count']} valid)  ",
        "",
        f"> **Disclaimer:** {report['disclaimer']}",
        "",
        "---",
        "",
        "## Manual Listening Checklist",
        "",
        "Rate each clip 1–5 on each dimension:",
        "",
        "| # | Dimension | 1 (low) | 5 (high) |",
        "|---|---|---|---|",
        "| 1 | **Bell clarity** | absent / washed | clear glass-bell attack and decay |",
        "| 2 | **Metallic ring** | no metallic character | prominent sustained metallic resonance |",
        "| 3 | **Darkness** | bright / clean | dark and textured |",
        "| 4 | **Shimmer** | no noise shimmer | prominent high-frequency shimmer tail |",
        "| 5 | **Space** | dry / close | deep reverberant space |",
        "",
        "Record scores as `clarity/ring/dark/shimmer/space` (e.g. `3/4/4/2/5`).",
        "",
        "---",
        "",
    ]

    # ── Spectral summary table ────────────────────────────────────────────────
    means = _strength_means(report["groups"], strengths)
    base = means.get(0.0, {})
    has_data = base.get("n", 0) > 0

    lines += [
        "## Spectral Summary by LoRA Strength",
        "",
        "Mean values across all 9 prompt×seed groups. Δ columns show difference "
        "from base (strength 0.00). Non-zero Δ indicates **measurable influence** "
        "of the LoRA at that scale; elevated air ratio is a **candidate shimmer signal** "
        "and elevated centroid indicates **high-frequency activity**.",
        "",
        "| Strength | n | RMS | Δ RMS | ZCR | Δ ZCR | Centroid Hz | Δ Centroid | Air Ratio | Δ Air |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in strengths:
        m = means.get(s, {})
        n = m.get("n", 0)
        lbl = f"{s:.2f}" + (" (base)" if s == 0.0 else "")
        if n == 0:
            lines.append(f"| {lbl} | 0 | — | — | — | — | — | — | — | — |")
            continue
        rms_s = f"{m['rms']:.4f}"
        zcr_s = f"{m['zcr']:.4f}"
        cen_s = f"{m['centroid']:.1f}"
        air_s = f"{m['air']:.4f}"
        if s == 0.0 or not has_data:
            d_rms = d_zcr = d_cen = d_air = "—"
        else:
            d_rms = f"{m['rms'] - base['rms']:+.4f}"
            d_zcr = f"{m['zcr'] - base['zcr']:+.4f}"
            d_cen = f"{m['centroid'] - base['centroid']:+.1f}"
            d_air = f"{m['air'] - base['air']:+.4f}"
        lines.append(
            f"| {lbl} | {n} | {rms_s} | {d_rms} | {zcr_s} | {d_zcr}"
            f" | {cen_s} | {d_cen} | {air_s} | {d_air} |"
        )
    lines.append("")

    # ── Per-group tables ──────────────────────────────────────────────────────
    lines += ["---", "", "## Results by Prompt × Seed", ""]

    for group in report["groups"]:
        pi, si = group["prompt_index"], group["seed_index"]
        lines += [
            f"### Group p{pi}_s{si} — Prompt {pi}, Seed {group['seed']}",
            "",
            f"**Prompt:** \"{group['prompt']}\"  ",
            f"**Seed:** {group['seed']}  ",
            "",
            "| Strength | File | RMS | ZCR | Centroid Hz | Air Ratio | Valid | Score | Notes |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for point in group["points"]:
            s = point["strength"]
            label = f"{s:.2f}" + (" (base)" if s == 0.0 else "")
            filename = Path(point["output"]).name
            stats = point.get("stats") or {}
            status = point.get("generation_status", "planned")
            if stats and stats.get("valid"):
                rms = f"{stats.get('rms', 0):.4f}"
                zcr = f"{stats.get('zcr', 0):.4f}"
                cen = f"{stats.get('spectral_centroid', 0):.1f}"
                air = f"{stats.get('air_ratio', 0):.4f}"
                tick = "✓"
            elif status in ("failed", "timeout", "error"):
                rms = zcr = cen = air = "ERR"
                tick = "✗"
            else:
                rms = zcr = cen = air = "—"
                tick = "—"
            lines.append(
                f"| {label} | `{filename}` | {rms} | {zcr} | {cen} | {air} | {tick}"
                " | `_/_/_/_/_` | |"
            )
        lines.append("")

    lines += [
        "---",
        "",
        "## Interpretation Guide",
        "",
        "- **RMS Δ**: energy shift introduced by the LoRA. Non-monotonic response "
        "is expected at rank 4 — the LoRA shifts timbre more than loudness.",
        "- **ZCR Δ**: proxy for high-frequency content. Positive Δ indicates "
        "measurable high-frequency activity relative to base.",
        "- **Centroid Δ**: spectral center of mass. Positive shift confirms "
        "candidate shimmer signal in upper frequency bands.",
        "- **Air Ratio Δ** (6–14 kHz band energy fraction): the clearest indicator "
        "of LoRA-driven shimmer character. Consistent positive Δ across strengths "
        "indicates measurable influence on the air band.",
        "- A U-shaped ZCR or air-ratio curve (high at 0.25 and 1.00, lower at 0.50/0.75) "
        "is typical of low-rank LoRAs interacting non-linearly with the diffusion schedule.",
        "- If 0.25 and 1.00 produce similar perceptual scores, the LoRA has low dynamic range "
        "— consider retraining at higher rank.",
        "- If 1.00 degrades noticeably vs 0.50, the optimal strength for production use is ≤ 0.75.",
        "",
        f"> {report['disclaimer']}",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


# ── Main verify flow ───────────────────────────────────────────────────────────

def verify_synthetic_lora_strength_sweep(
    *,
    run_generation: bool = False,
    model_version_id: str = MODEL_VERSION_ID,
    training_run_id: str = TRAINING_RUN_ID,
    mandatory_sweep: bool = True,
) -> dict[str, Any]:
    if not is_sweep_enabled(run_generation):
        raise RuntimeError(
            f"LoRA strength sweep is gated. Set {GATE_ENV}=1 or pass --run."
        )

    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()

    # ── Step 1: load Model Version and TrainingRun ────────────────────────────
    print(f"Step 1: loading Model Version {model_version_id}…")
    style_store = StyleVersionStore(settings.style_versions_dir)
    model_version = style_store.get(model_version_id)
    if model_version is None:
        raise RuntimeError(f"Model Version not found: {model_version_id}")

    run_store = TrainingRunStore(settings.training_runs_dir)
    training_run = run_store.get(training_run_id)
    if training_run is None:
        raise RuntimeError(f"TrainingRun not found: {training_run_id}")

    lineage_ok, lineage_failures = validate_sweep_lineage(
        model_version, training_run, expected_training_run_id=training_run_id
    )
    print(f"  Lineage: {'ok' if lineage_ok else 'FAILED — ' + str(lineage_failures)}")

    # ── Step 2: resolve LoRA path ─────────────────────────────────────────────
    print("Step 2: resolving LoRA load path…")
    style_svc = StyleVersionService(style_store)
    try:
        lora_load_path_str = style_svc.resolve_load_path(model_version_id, settings.data_dir)
    except Exception as exc:
        raise RuntimeError(f"Cannot resolve LoRA load path: {exc}") from exc

    lora_dir = Path(lora_load_path_str)
    lora_naming = validate_lora_files(lora_dir)
    lora_available = lora_naming["ok"]
    print(f"  LoRA path: {lora_load_path_str}  files_ok={lora_available}")

    if not lora_available:
        raise RuntimeError(
            f"LoRA files missing or empty at {lora_dir}. Check: {lora_naming}"
        )

    # ── Step 3: plan sweep groups ─────────────────────────────────────────────
    print("Step 3: planning sweep groups…")
    experiment_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    experiment_dir = (
        settings.data_dir
        / "experiments"
        / "synthetic-dark-bell-lora-strength-sweep"
        / experiment_ts
    )
    experiment_dir.mkdir(parents=True, exist_ok=True)
    groups = plan_sweep_groups(experiment_dir, lora_load_path_str, lora_available=lora_available)
    total_points = sum(len(g["points"]) for g in groups)
    print(f"  {len(groups)} groups × {len(SWEEP_STRENGTHS)} strengths = {total_points} clips")

    # ── Step 4: run sweep ─────────────────────────────────────────────────────
    print(f"Step 4: generating {total_points} clips…")
    groups = run_sweep(groups, settings, mandatory=mandatory_sweep)

    generated_count = sum(
        1 for g in groups for p in g["points"] if p["generation_status"] == "succeeded"
    )
    valid_count = sum(
        1 for g in groups for p in g["points"]
        if p.get("stats") and p["stats"].get("valid")
    )
    sweep_ok = (generated_count == total_points and valid_count == total_points) or not mandatory_sweep
    print(f"  Generated: {generated_count}/{total_points}  Valid: {valid_count}/{total_points}")

    # ── Step 5: write reports ─────────────────────────────────────────────────
    print("Step 5: writing reports…")
    report: dict[str, Any] = {
        "phase": "synthetic-dark-bell-v1-lora-strength-sweep",
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": SWEEP_DISCLAIMER,
        "model_version": {
            "id": model_version_id,
            "base_model_name": model_version.base_model_name,
            "training_run_id": model_version.training_run_id,
            "artifact_type": model_version.artifact_type,
        },
        "training_run_id": training_run_id,
        "lora_load_path": lora_load_path_str,
        "lora_naming": lora_naming,
        "lineage_ok": lineage_ok,
        "lineage_failures": lineage_failures,
        "sweep_strengths": SWEEP_STRENGTHS,
        "prompts": list(SWEEP_PROMPTS),
        "seeds": list(SWEEP_SEEDS),
        "groups": groups,
        "total_points": total_points,
        "generated_count": generated_count,
        "valid_count": valid_count,
        "sweep_ok": sweep_ok,
        "success": lineage_ok and lora_available and sweep_ok,
        "error": None,
    }

    report_path = experiment_dir / "report.json"
    report_md_path = experiment_dir / "report.md"
    report["report_path"] = str(report_path)
    report["report_md_path"] = str(report_md_path)

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_report_md(report, report_md_path)

    status = "PASS" if report["success"] else "FAIL"
    print(f"\nSynthetic Dark Bell v1 LoRA Strength Sweep: {status}")
    print(f"  Lineage: {'ok' if lineage_ok else 'FAILED'}")
    print(f"  Generated: {generated_count}/{total_points}  Valid: {valid_count}/{total_points}")
    print(f"  Report JSON: {report_path}")
    print(f"  Report MD:   {report_md_path}")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synthetic Dark Bell v1 LoRA Strength Sweep"
    )
    parser.add_argument("--run", action="store_true",
                        help=f"Enable real generation (requires {GATE_ENV}=1 or this flag)")
    parser.add_argument("--model-version-id", default=MODEL_VERSION_ID)
    parser.add_argument("--training-run-id", default=TRAINING_RUN_ID)
    parser.add_argument("--allow-planned-sweep", action="store_true",
                        help="Allow planned/skipped clips without failing the report")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not is_sweep_enabled(args.run):
        print(
            f"LoRA strength sweep is gated. "
            f"Set {GATE_ENV}=1 or pass --run to execute. No generation was run."
        )
        return 0

    report = verify_synthetic_lora_strength_sweep(
        run_generation=args.run,
        model_version_id=args.model_version_id,
        training_run_id=args.training_run_id,
        mandatory_sweep=not args.allow_planned_sweep,
    )
    if args.json:
        print(json.dumps(report, indent=2))
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
