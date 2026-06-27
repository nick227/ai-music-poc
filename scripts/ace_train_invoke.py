#!/usr/bin/env python3
"""Invoke ACE train.py with an expanded path-safety root for Studio run dirs."""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ACE_STEP_DIR = Path("/home/administrator/models/ACE-Step-1.5")


def _configure_safe_root() -> None:
    ace_step = Path(os.environ.get("ACE_STEP_DIR", str(DEFAULT_ACE_STEP_DIR))).resolve()
    default_root = ace_step.parent.parent
    safe_root = Path(os.environ.get("ACE_TRAIN_SAFE_ROOT", str(default_root))).expanduser().resolve()
    if str(ace_step) not in sys.path:
        sys.path.insert(0, str(ace_step))
    from acestep.training.path_safety import set_safe_root

    set_safe_root(str(safe_root))


def main() -> None:
    ace_step = Path(os.environ.get("ACE_STEP_DIR", str(DEFAULT_ACE_STEP_DIR))).resolve()
    train_script = ace_step / "train.py"
    if not train_script.is_file():
        raise SystemExit(f"ACE train.py not found: {train_script}")

    _configure_safe_root()
    os.chdir(ace_step)
    sys.argv[0] = str(train_script)
    runpy.run_path(str(train_script), run_name="__main__")


if __name__ == "__main__":
    main()
