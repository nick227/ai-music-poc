#!/usr/bin/env python3
"""
Install ACE DiT checkpoints into ACE_MODEL_DIR (outside the app repo).

Recommended top-quality model: acestep-v15-xl-sft (4B XL, 24–50 steps with offload).
Optional fast XL: acestep-v15-xl-turbo.

After installation, run:
  python scripts/ace_readiness.py --keep-output
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from app.core.ace_checkpoint_layout import dit_checkpoint_folder_ready, describe_checkpoint_layout
from app.core.config import get_settings
from app.generators.ace_step.env import ace_subprocess_env

DEFAULT_MODEL = "acestep-v15-xl-sft"
HF_REPOS = {
    "acestep-v15-xl-sft": "ACE-Step/acestep-v15-xl-sft",
    "acestep-v15-xl-turbo": "ACE-Step/acestep-v15-xl-turbo",
    "acestep-v15-xl-base": "ACE-Step/acestep-v15-xl-base",
    # Legacy 2B — install only if explicitly requested
    "acestep-v15-sft": "ACE-Step/acestep-v15-sft",
    "acestep-v15-base": "ACE-Step/acestep-v15-base",
}


def _ace_step_dir(settings, override: str | None = None) -> Path:
    raw = (override or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    if settings.ace_step_dir:
        return Path(settings.ace_step_dir).expanduser().resolve()
    default = Path("/home/administrator/models/ACE-Step-1.5")
    if default.is_dir():
        return default
    raise SystemExit("ACE_STEP_DIR is required; set it in .env or pass --ace-step-dir")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download an ACE DiT checkpoint into ACE_MODEL_DIR")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        choices=sorted(HF_REPOS),
        help=f"DiT checkpoint to install (default: {DEFAULT_MODEL})",
    )
    parser.add_argument("--ace-step-dir", help="ACE-Step checkout root; defaults to ACE_STEP_DIR from Settings/.env")
    parser.add_argument("--force", action="store_true", help="Re-download even if already present")
    parser.add_argument("--dry-run", action="store_true", help="Check availability without downloading")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()

    model_name = args.model
    hf_repo = HF_REPOS[model_name]
    checkpoint_dir = settings.ace_model_dir.expanduser().resolve()
    ace_python = settings.ace_python
    ace_step_dir = _ace_step_dir(settings, args.ace_step_dir)

    print(f"Target checkpoint dir: {checkpoint_dir}")
    print(f"ACE venv python:       {ace_python}")
    print(f"ACE-Step source dir:   {ace_step_dir}")
    print(f"Model to install:      {model_name}  (HF: {hf_repo})")
    print()

    target = checkpoint_dir / model_name
    if dit_checkpoint_folder_ready(target) and not args.force:
        print(f"Already installed at {target}")
        if model_name.startswith("acestep-v15-xl"):
            print("XL model ready for experimental final-render profiles.")
        print("\nRe-run validation:  python scripts/ace_readiness.py --keep-output")
        return 0

    if args.dry_run:
        status = "present" if dit_checkpoint_folder_ready(target) else "NOT installed"
        print(f"[dry-run] {model_name}: {status}")
        if not dit_checkpoint_folder_ready(target):
            print(f"[dry-run] Would download from HF repo: {hf_repo}")
        return 0

    download_code = f"""
import sys
sys.path.insert(0, {repr(str(ace_step_dir))})
from pathlib import Path
from acestep.model_downloader import ensure_dit_model

checkpoint_dir = Path({repr(str(checkpoint_dir))})
checkpoint_dir.mkdir(parents=True, exist_ok=True)

print(f"Downloading {model_name} → {{checkpoint_dir}} ...")
success, msg = ensure_dit_model({repr(model_name)}, checkpoints_dir=checkpoint_dir)
print(msg)
sys.exit(0 if success else 1)
""".replace("model_name", repr(model_name))

    env = ace_subprocess_env(settings)
    env["ACESTEP_CHECKPOINTS_DIR"] = str(checkpoint_dir)
    env["HF_HUB_DISABLE_PROGRESS_BARS"] = "0"

    print(f"Downloading {model_name} via ACE-Step model_downloader ...")
    print("(This may take several minutes on first download.)\n")

    result = subprocess.run(
        [str(ace_python), "-c", download_code],
        cwd=str(ace_step_dir),
        env=env,
        text=True,
    )

    if result.returncode != 0:
        print(f"\nDownload failed (exit {result.returncode}).", file=sys.stderr)
        print("Manual alternative:", file=sys.stderr)
        print(
            f"  huggingface-cli download {hf_repo} --local-dir {checkpoint_dir / model_name}",
            file=sys.stderr,
        )
        return result.returncode

    if not dit_checkpoint_folder_ready(target):
        print(
            f"\nDownload reported success but checkpoint weights not found under {target}.",
            file=sys.stderr,
        )
        return 1

    print(f"\n{model_name} installed at {target} ({describe_checkpoint_layout(target)})")
    print("\nNext step — re-run the readiness check to update the hardware profile:")
    print("  python scripts/ace_readiness.py --keep-output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
