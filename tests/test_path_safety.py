import pytest

from app.core.paths import safe_child_path


def test_safe_child_path_blocks_escape(tmp_path):
    with pytest.raises(ValueError):
        safe_child_path(tmp_path, "../escape.wav")


def test_safe_child_path_accepts_child(tmp_path):
    path = safe_child_path(tmp_path, "ok.wav")
    assert path.parent == tmp_path.resolve()
