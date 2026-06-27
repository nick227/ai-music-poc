#!/usr/bin/env python3
"""Run acestep.training_v2.cli.train_fixed with a soundfile torchaudio shim."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.training.ace_torchaudio_shim  # noqa: F401
from acestep.training_v2.cli.train_fixed import main

if __name__ == "__main__":
    raise SystemExit(main())
