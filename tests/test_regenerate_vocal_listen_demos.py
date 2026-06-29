import os
import subprocess
import sys
from pathlib import Path

from scripts.regenerate_vocal_listen_demos import DEFAULT_OUTPUT_DIR, regenerate_cases, resolve_output_dir


def test_regenerate_overwrites_stable_wav_paths(tmp_path: Path):
    output_dir = tmp_path / "vocal-plan-v01"
    first = regenerate_cases(output_dir, duration_seconds=10)
    first_mtime = os.path.getmtime(first[0])
    second = regenerate_cases(output_dir, duration_seconds=10)
    assert [path.name for path in first] == ["pop_chorus.wav", "rap_dense.wav", "ballad_held.wav"]
    assert [path.resolve() for path in first] == [path.resolve() for path in second]
    assert os.path.getmtime(second[0]) >= first_mtime
    for path in second:
        assert path.exists()
        assert path.stat().st_size > 1000


def test_regenerate_timestamped_writes_new_subdirectory(tmp_path: Path):
    base = tmp_path / "vocal-plan-v01"
    stable = resolve_output_dir(base, timestamped=False)
    stamped = resolve_output_dir(base, timestamped=True)
    assert stable == base
    assert stamped != base
    assert stamped.parent == base
    written = regenerate_cases(stamped, duration_seconds=10)
    assert all(path.parent == stamped for path in written)
    assert not (base / "pop_chorus.wav").exists()


def test_regenerate_script_help():
    subprocess.run(
        [sys.executable, "scripts/regenerate_vocal_listen_demos.py", "--help"],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )


def test_default_output_dir_points_at_repo_experiment_folder():
    assert DEFAULT_OUTPUT_DIR.as_posix().endswith("data/experiments/vocal-plan-v01")
