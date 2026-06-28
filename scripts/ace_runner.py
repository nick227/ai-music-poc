#!/usr/bin/env python3
"""
Bridge between our app's ACE_COMMAND_TEMPLATE and ACE-Step cli.py.

Dry-run mode validates wiring only — no torch/transformers/diffusers imports.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def ace_step_dir() -> Path | None:
    raw = os.environ.get("ACE_STEP_DIR", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def ace_venv_python(step_dir: Path) -> Path:
    return step_dir / ".venv" / "bin" / "python"


def ace_cli_script(step_dir: Path) -> Path:
    return (step_dir / "cli.py").resolve()


def resolve_optional_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    if raw.strip().lower() in {"__none__", "none", "null", "false"}:
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


def toml_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if value is None:
        return '""'
    return json.dumps(str(value))


def write_config(path: Path, values: dict[str, object]) -> None:
    lines = [f"{key} = {toml_value(value)}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_lm_sitecustomize(path: Path) -> None:
    """Patch builtins.input so the ACE LM thinking hook never blocks headlessly.

    ACE's _edit_formatted_prompt_via_file writes the LM-generated CoT to
    instruction.txt, calls input() to wait for user edits, then reads the file
    back.  When stdin is not a TTY (our subprocess case), input() raises
    EOFError and the generation crashes.  This patch makes input() return ""
    immediately when stdin is not interactive, which causes the function to
    read instruction.txt right back — effectively using the LM's own output
    without interactive editing.
    """
    path.write_text(
        """
import builtins
import sys

_orig_input = builtins.input


def _headless_input(prompt=""):
    if not sys.stdin.isatty():
        return ""
    return _orig_input(prompt)


builtins.input = _headless_input
""".lstrip(),
        encoding="utf-8",
    )


def write_lora_sitecustomize(path: Path) -> None:
    path.write_text(
        """
import builtins
import json
import os
import sys
from pathlib import Path

# Patch input() so the ACE LM thinking hook never blocks headlessly.
_orig_input = builtins.input


def _headless_input(prompt=""):
    if not sys.stdin.isatty():
        return ""
    return _orig_input(prompt)


builtins.input = _headless_input


_step_dir = os.environ.get("ACE_STUDIO_STEP_DIR", "").strip()
if _step_dir:
    sys.path.insert(0, _step_dir)

from acestep.handler import AceStepHandler

_original_initialize_service = AceStepHandler.initialize_service


def _write_lora_meta(payload):
    meta_path = os.environ.get("ACE_STUDIO_LORA_META_FILE", "").strip()
    if not meta_path:
        return
    Path(meta_path).write_text(json.dumps(payload), encoding="utf-8")


def _studio_initialize_service(self, *args, **kwargs):
    result = _original_initialize_service(self, *args, **kwargs)
    lora_path = os.environ.get("ACE_STUDIO_LORA_PATH", "").strip()
    scale_raw = os.environ.get("ACE_STUDIO_LORA_SCALE", "1.0")
    try:
        scale = float(scale_raw)
    except ValueError:
        scale = 1.0
    meta = {
        "loraLoadAttempted": bool(lora_path),
        "loraLoadSucceeded": False,
        "loraLoadMessage": "",
        "loraPath": lora_path,
        "loraScale": scale if lora_path else None,
    }
    if lora_path:
        try:
            message = self.load_lora(lora_path)
            meta["loraLoadMessage"] = str(message)
            meta["loraLoadSucceeded"] = True
            print(f"[ace_runner] load_lora: {message}", flush=True)
            scale_message = self.set_lora_scale(scale)
            print(f"[ace_runner] set_lora_scale: {scale_message}", flush=True)
            toggle_message = self.set_use_lora(True)
            print(f"[ace_runner] set_use_lora: {toggle_message}", flush=True)
        except Exception as exc:
            meta["loraLoadMessage"] = str(exc)
            print(f"[ace_runner] load_lora: {exc}", flush=True)
        _write_lora_meta(meta)
    return result


AceStepHandler.initialize_service = _studio_initialize_service
""".lstrip(),
        encoding="utf-8",
    )


def ace_meta_sidecar_path(output_path: Path) -> Path:
    return output_path.with_name(f"{output_path.stem}.ace_meta.json")


def build_lora_meta(
    *,
    use_lora: bool,
    lora_path: Path | None,
    lora_scale: float,
    hook_meta: dict[str, object] | None = None,
    stdout: str = "",
    stderr: str = "",
) -> dict[str, object]:
    if hook_meta:
        return {
            "loraLoadAttempted": bool(hook_meta.get("loraLoadAttempted")),
            "loraLoadSucceeded": bool(hook_meta.get("loraLoadSucceeded")),
            "loraLoadMessage": str(hook_meta.get("loraLoadMessage") or ""),
            "loraPath": str(hook_meta.get("loraPath") or ""),
            "loraScale": hook_meta.get("loraScale"),
        }
    if use_lora:
        message = ""
        succeeded = False
        for line in f"{stdout}\n{stderr}".splitlines():
            if "[ace_runner] load_lora:" in line:
                message = line.split("[ace_runner] load_lora:", 1)[1].strip()
                succeeded = bool(message) and "error" not in message.lower() and "fail" not in message.lower()
        return {
            "loraLoadAttempted": True,
            "loraLoadSucceeded": succeeded,
            "loraLoadMessage": message,
            "loraPath": str(lora_path) if lora_path else "",
            "loraScale": lora_scale,
        }
    return {
        "loraLoadAttempted": False,
        "loraLoadSucceeded": False,
        "loraLoadMessage": "",
        "loraPath": "",
        "loraScale": None,
    }


def write_ace_meta_sidecar(output_path: Path, payload: dict[str, object]) -> Path:
    path = ace_meta_sidecar_path(output_path)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def emit_lora_meta_line(payload: dict[str, object]) -> None:
    print(f"[ace_runner] lora_meta={json.dumps(payload, separators=(',', ':'))}", flush=True)


def dry_run_lines(args: argparse.Namespace) -> list[str]:
    step_dir = ace_step_dir()
    venv_python = ace_venv_python(step_dir) if step_dir else None
    cli_script = ace_cli_script(step_dir) if step_dir else None

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
        f"ACE_STEP_DIR={step_dir if step_dir else '(not set)'} exists={step_dir.exists() if step_dir else False}",
        f"ACE_VENV={venv_python if venv_python else '(not set)'} exists={venv_python.exists() if venv_python else False}",
        f"ACE_CLI={cli_script if cli_script else '(not set)'} exists={cli_script.exists() if cli_script else False}",
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
        f"offload_to_cpu={args.offload_to_cpu} use_lm={args.use_lm} lm_model={args.lm_model or '(none)'}",
        f"use_lora={args.use_lora} lora_path={args.lora_path or '(not set)'} lora_scale={args.lora_scale}",
        "",
        "== Voice passthrough (app template only; ACE CLI ignores today) ==",
        f"singing_voice={args.singing_voice} vocal_intensity={args.vocal_intensity} vocal_style={args.vocal_style!r}",
    ]
    return lines


def missing_dry_run_paths() -> list[str]:
    step_dir = ace_step_dir()
    if step_dir is None:
        return ["ACE_STEP_DIR"]
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
    parser.add_argument("--lora-path", default="")
    parser.add_argument("--lora-scale", type=float, default=1.0)
    parser.add_argument("--use-lora", default="false")
    parser.add_argument("--offload-to-cpu", action="store_true", help="Enable CPU offload to reduce GPU VRAM usage")
    parser.add_argument("--use-lm", default="false", help="Enable 5Hz language model preprocessing (true/false)")
    parser.add_argument("--lm-model", default="", help="LM model subfolder or path (e.g. acestep-5Hz-lm-0.6B)")
    parser.add_argument("--dry-run", action="store_true", help="Validate wiring without running ACE-Step inference")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.dry_run:
        return run_dry_run(args)

    if not args.prompt_file or not args.lyrics_file or not args.output:
        build_parser().error("--prompt-file, --lyrics-file, and --output are required unless --dry-run is set")

    step_dir = ace_step_dir()
    if step_dir is None:
        print("[ace_runner] ERROR: ACE_STEP_DIR is required", file=sys.stderr)
        return 2
    venv_python = ace_venv_python(step_dir)
    cli_script = ace_cli_script(step_dir)

    negative_file = args.negative_prompt_file or args.negative_file
    caption = Path(args.prompt_file).read_text(encoding="utf-8").strip()
    lyrics_path = Path(args.lyrics_file).resolve()
    output_path = Path(args.output).resolve()
    lora_path = resolve_optional_path(args.lora_path)
    use_lora = str(args.use_lora).lower() in {"1", "true", "yes", "on"} and lora_path is not None
    if use_lora:
        missing = [
            path.name
            for path in [lora_path / "adapter_config.json", lora_path / "adapter_model.safetensors"]
            if not path.is_file()
        ]
        if missing:
            print(f"[ace_runner] ERROR: LoRA adapter is missing required files: {', '.join(missing)}", file=sys.stderr)
            return 2
    lyrics_text = lyrics_path.read_text(encoding="utf-8").strip() if lyrics_path.exists() else ""
    if negative_file and Path(negative_file).exists():
        negative = Path(negative_file).read_text(encoding="utf-8").strip()
        if negative:
            caption = f"{caption}\n\nAvoid: {negative}"

    with tempfile.TemporaryDirectory(prefix="ace_out_") as save_dir:
        config_path = Path(save_dir) / "ace_config.toml"
        quality_steps = {"draft": 8, "balanced": 24, "high": 50}
        seed = args.seed if args.seed is not None and args.seed >= 0 else -1
        use_lm = str(args.use_lm).lower() in {"1", "true", "yes", "on"}
        lm_model_name = args.lm_model.strip() if args.lm_model else ""
        checkpoint_dir_str = str(Path(args.model_dir).expanduser().resolve()) if args.model_dir else os.environ.get("ACESTEP_CHECKPOINTS_DIR", "")
        # Resolve lm_model_path: name relative to checkpoint_dir, or absolute path
        lm_model_path: str | None = None
        if use_lm and lm_model_name:
            candidate = Path(checkpoint_dir_str) / lm_model_name
            if candidate.exists():
                lm_model_path = str(candidate)
            elif Path(lm_model_name).is_absolute() and Path(lm_model_name).exists():
                lm_model_path = lm_model_name
            else:
                lm_model_path = lm_model_name  # pass as-is; ACE will resolve or error
        write_config(config_path, {
            "project_root": str(step_dir),
            "checkpoint_dir": checkpoint_dir_str,
            "backend": "pt",
            "device": args.device,
            "save_dir": save_dir,
            "audio_format": "wav",
            "caption": caption,
            "lyrics": lyrics_text,
            "duration": args.duration,
            "seed": seed,
            "use_random_seed": seed < 0,
            "guidance_scale": args.guidance_scale,
            "inference_steps": quality_steps.get(args.quality, 24),
            "batch_size": 1,
            "offload_to_cpu": args.offload_to_cpu,
            "thinking": use_lm,
            "lm_model_path": lm_model_path or "",
            "use_cot_metas": False,
            "use_cot_caption": False,
            "use_cot_lyrics": False,
            "use_cot_language": False,
            "sample_mode": False,
            "use_format": False,
            "instrumental": False,
            "task_type": "text2music",
            "use_lora": use_lora,
            "lora_path": str(lora_path) if use_lora else "",
            "lora_scale": args.lora_scale if use_lora else 1.0,
        })
        cmd: list[str] = [
            str(venv_python),
            str(cli_script),
            "--config", str(config_path),
            "--backend", "pt",
            "--log-level", "WARNING",
        ]

        env = os.environ.copy()
        if args.model_dir:
            env["ACESTEP_CHECKPOINTS_DIR"] = str(Path(args.model_dir).expanduser().resolve())
        meta_file = ace_meta_sidecar_path(output_path)
        hook_meta: dict[str, object] | None = None

        # When using the LM (thinking=True) inject a sitecustomize that patches
        # builtins.input so the ACE prompt-editing hook doesn't block headlessly.
        if use_lm:
            lm_hook_dir = Path(save_dir) / "studio_lm_hook"
            lm_hook_dir.mkdir(parents=True, exist_ok=True)
            write_lm_sitecustomize(lm_hook_dir / "sitecustomize.py")
            env["PYTHONPATH"] = f"{lm_hook_dir}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)

        if use_lora:
            hook_dir = Path(save_dir) / "studio_lora_hook"
            hook_dir.mkdir(parents=True, exist_ok=True)
            write_lora_sitecustomize(hook_dir / "sitecustomize.py")
            env["ACE_STUDIO_LORA_PATH"] = str(lora_path)
            env["ACE_STUDIO_LORA_SCALE"] = str(args.lora_scale)
            env["ACE_STUDIO_STEP_DIR"] = str(step_dir)
            env["ACE_STUDIO_LORA_META_FILE"] = str(meta_file)
            env["PYTHONPATH"] = f"{hook_dir}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
        print(f"[ace_runner] Running: {shlex.join(cmd)}", flush=True)
        result = subprocess.run(cmd, cwd=str(step_dir), text=True, capture_output=True, env=env)
        if use_lora and meta_file.is_file():
            try:
                hook_meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                hook_meta = None
        lora_meta = build_lora_meta(
            use_lora=use_lora,
            lora_path=lora_path,
            lora_scale=args.lora_scale,
            hook_meta=hook_meta,
            stdout=result.stdout,
            stderr=result.stderr,
        )
        if result.returncode != 0:
            write_ace_meta_sidecar(output_path, lora_meta)
            emit_lora_meta_line(lora_meta)
            if result.stdout:
                print(result.stdout[-4000:], flush=True)
            if result.stderr:
                print(result.stderr[-4000:], file=sys.stderr)
            print(f"[ace_runner] ACE-Step exited with {result.returncode}", file=sys.stderr)
            return result.returncode
        if result.stdout:
            print(result.stdout[-4000:], flush=True)
        if result.stderr:
            print(result.stderr[-2000:], flush=True)

        wavs = list(Path(save_dir).glob("**/*.wav"))
        if not wavs:
            lora_meta["loraLoadMessage"] = lora_meta.get("loraLoadMessage") or "No WAV output found"
            write_ace_meta_sidecar(output_path, lora_meta)
            emit_lora_meta_line(lora_meta)
            print("[ace_runner] ERROR: No WAV output found in save_dir", file=sys.stderr)
            return 1
        wavs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(wavs[0]), str(output_path))
        write_ace_meta_sidecar(output_path, lora_meta)
        emit_lora_meta_line(lora_meta)
        print(f"[ace_runner] Wrote {output_path} ({output_path.stat().st_size} bytes)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
