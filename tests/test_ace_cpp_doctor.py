"""Tests verifying the ACE.cpp doctor checks the right binaries."""
from __future__ import annotations

import io
import sys
from unittest.mock import patch

from scripts.ace_cpp_doctor import main


def _run_doctor_with_paths(existing_paths: set[str]) -> str:
    """Run main() with os.path.exists stubbed and capture stdout."""
    def fake_exists(p):
        return str(p) in existing_paths

    buf = io.StringIO()
    with patch("scripts.ace_cpp_doctor.os.path.exists", side_effect=fake_exists), \
         patch("scripts.ace_cpp_doctor.os.listdir", return_value=[]), \
         patch("scripts.ace_cpp_doctor.shutil.which", return_value=None), \
         patch("sys.stdout", buf):
        main()
    return buf.getvalue()


REPO = "/home/administrator/models/acestep.cpp"
BINARY_LM = f"{REPO}/build/ace-lm"
BINARY_SYNTH = f"{REPO}/build/ace-synth"


def test_doctor_reports_both_binaries_found():
    output = _run_doctor_with_paths({REPO, BINARY_LM, BINARY_SYNTH})
    assert "ace-lm" in output
    assert "ace-synth" in output
    assert "✓" in output or "[OK]" in output or "exists" in output.lower()


def test_doctor_reports_missing_ace_lm():
    output = _run_doctor_with_paths({REPO, BINARY_SYNTH})
    assert "ace-lm" in output
    assert BINARY_LM in output


def test_doctor_reports_missing_ace_synth():
    output = _run_doctor_with_paths({REPO, BINARY_LM})
    assert "ace-synth" in output
    assert BINARY_SYNTH in output


def test_doctor_does_not_check_ace_server():
    """ace-server was the wrong binary; the doctor must not reference it."""
    output = _run_doctor_with_paths({REPO})
    assert "ace-server" not in output
