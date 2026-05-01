from __future__ import annotations

from pathlib import Path

from homebase.core import setup_tools as setup_tools


def test_compact_path_for_display_uses_tilde() -> None:
    home = Path.home()
    out = setup_tools.compact_path_for_display(str(home / "x"))
    assert out.startswith("~")


def test_has_any_tmux_save_binding_detects_bind_line() -> None:
    text = 'bind-key t run-shell -b "uv run --script b.py b tmux save"\n'
    assert setup_tools.has_any_tmux_save_binding(text) is True


def test_recommended_tmux_save_binding_contains_expected_parts() -> None:
    line = setup_tools.recommended_tmux_save_binding(Path("/tmp/b"), "/usr/bin/uv", "/usr/bin/tmux")
    assert "TMUX_BIN=" in line
    assert "tmux save" in line
