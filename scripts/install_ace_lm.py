#!/usr/bin/env python3
"""
Install the recommended safe-tier LM checkpoint for ACE-Step.

ACE's own tier recommendation for <= 12 GB VRAM is acestep-5Hz-lm-0.6B.
This script uses ACE-Step's model_downloader so the checkpoint lands in
the same directory as the rest of the ACE checkpoints.

After installation, run:
  python scripts/ace_readiness.py --keep-output
to re-validate and update data/ace_hardware_profile.json.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

from app.core.config import get_settings
from app.generators.ace_step.env import ace_subprocess_env

MODEL_NAME = "acestep-5Hz-lm-0.6B"
HF_REPO = "ACE-Step/acestep-5Hz-lm-0.6B"


def _ace_step_dir(settings, override: str | None = None) -> Path:
    raw = (override or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    if settings.ace_step_dir:
        return Path(settings.ace_step_dir).expanduser().resolve()
    # Hard fallback so the script always uses the canonical installation
    default = Path("/home/administrator/models/ACE-Step-1.5")
    if default.is_dir():
        return default
    raise SystemExit("ACE_STEP_DIR is required; set it in .env or pass --ace-step-dir")


def main() -> int:
    parser = argparse.ArgumentParser(description=f"Download {MODEL_NAME} into ACE_MODEL_DIR")
    parser.add_argument("--ace-step-dir", help="ACE-Step checkout root; defaults to ACE_STEP_DIR from Settings/.env")
    parser.add_argument("--force", action="store_true", help="Re-download even if already present")
    parser.add_argument("--dry-run", action="store_true", help="Check availability without downloading")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    get_settings.cache_clear()
    settings = get_settings()

    checkpoint_dir = settings.ace_model_dir.expanduser().resolve()
    ace_python = settings.ace_python
    ace_step_dir = _ace_step_dir(settings, args.ace_step_dir)

    print(f"Target checkpoint dir: {checkpoint_dir}")
    print(f"ACE venv python:       {ace_python}")
    print(f"ACE-Step source dir:   {ace_step_dir}")
    print(f"Model to install:      {MODEL_NAME}  (HF: {HF_REPO})")
    print()

    target = checkpoint_dir / MODEL_NAME
    if target.exists() and not args.force:
        print(f"Already installed at {target}")
        print(f"Safe profile will use {MODEL_NAME}.")
        print(f"\nRe-run validation:  python scripts/ace_readiness.py --keep-output")
        return 0

    if args.dry_run:
        status = "present" if target.exists() else "NOT installed"
        print(f"[dry-run] {MODEL_NAME}: {status}")
        if not target.exists():
            print(f"[dry-run] Would download from HF repo: {HF_REPO}")
        return 0

    # Use ACE-Step's own model_downloader via the ACE venv python so it respects
    # ACESTEP_CHECKPOINTS_DIR and uses the same HF credentials / cache.
    download_code = f"""
import sys
sys.path.insert(0, {repr(str(ace_step_dir))})
from pathlib import Path
from acestep.model_downloader import ensure_lm_model

checkpoint_dir = Path({repr(str(checkpoint_dir))})
checkpoint_dir.mkdir(parents=True, exist_ok=True)

print(f"Downloading {MODEL_NAME} → {{checkpoint_dir}} ...")
success, msg = ensure_lm_model({repr(MODEL_NAME)}, checkpoints_dir=checkpoint_dir)
print(msg)
sys.exit(0 if success else 1)
""".replace("MODEL_NAME", repr(MODEL_NAME))

    env = ace_subprocess_env(settings)
    env["ACESTEP_CHECKPOINTS_DIR"] = str(checkpoint_dir)
    env["HF_HUB_DISABLE_PROGRESS_BARS"] = "0"  # show progress

    print(f"Downloading {MODEL_NAME} via ACE-Step model_downloader ...")
    print("(This may take a few minutes on first download.)\n")

    result = subprocess.run(
        [str(ace_python), "-c", download_code],
        cwd=str(ace_step_dir),
        env=env,
        text=True,
    )

    if result.returncode != 0:
        print(f"\nDownload failed (exit {result.returncode}).", file=sys.stderr)
        print("Manual alternative:", file=sys.stderr)
        print(f"  huggingface-cli download {HF_REPO} --local-dir {checkpoint_dir / MODEL_NAME}", file=sys.stderr)
        return result.returncode

    installed = (checkpoint_dir / MODEL_NAME).exists()
    if not installed:
        print(f"\nDownload reported success but {target} not found.", file=sys.stderr)
        return 1

    print(f"\n{MODEL_NAME} installed at {target}")
    print(f"\nNext step — re-run the readiness check to update the safe profile:")
    print(f"  python scripts/ace_readiness.py --keep-output")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
