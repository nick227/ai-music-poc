"""Example ACE-Step runner contract.

This is a stub for documentation. Replace the body with your real ACE-Step invocation.
It should read the request JSON and write a WAV to --out.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    print(f"ACE-Step stub received title={request.get('title')!r}; no model is installed.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
