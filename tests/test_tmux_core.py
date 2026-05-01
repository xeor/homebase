from __future__ import annotations

from pathlib import Path

import pytest

from homebase.tmux import core as tmux_core


def test_tmux_parse_rows_filters_bad_lines() -> None:
    raw = "a\tb\nc\td\te\n x\t y\n"
    assert tmux_core.tmux_parse_rows(raw, 2) == [["a", "b"], ["x", "y"]]


def test_first_token_basename_handles_shell_and_plain_split() -> None:
    assert tmux_core.first_token_basename("/usr/bin/python -m pytest") == "python"
    assert tmux_core.first_token_basename('"unterminated') == '"unterminated'


def test_resolve_tmux_save_output_defaults_to_project_file(tmp_path: Path) -> None:
    out = tmux_core.resolve_tmux_save_output("", tmp_path)
    assert out == tmp_path / ".tmuxp.yaml"


def test_format_error_prefers_message() -> None:
    err = RuntimeError("boom")
    assert tmux_core.format_error(err) == "RuntimeError: boom"


def test_resolve_project_root_from_panes_single_root(tmp_path: Path) -> None:
    base_root = tmp_path / "base"
    project = base_root / "proj"
    nested = project / "src"
    nested.mkdir(parents=True)

    def _is_under(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    def _find_marker_root_upward(path: Path) -> Path | None:
        cur = path.resolve()
        if _is_under(cur, project):
            return project
        return None

    resolved, debug = tmux_core.resolve_project_root_from_panes(
        [str(nested)],
        base_root,
        is_under=_is_under,
        find_marker_root_upward=_find_marker_root_upward,
    )

    assert resolved == project
    assert debug["resolved_project_root"] == str(project)


def test_resolve_project_root_from_panes_raises_on_multiple_roots(tmp_path: Path) -> None:
    base_root = tmp_path / "base"
    a = base_root / "a" / "x"
    b = base_root / "b" / "y"
    a.mkdir(parents=True)
    b.mkdir(parents=True)

    def _is_under(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False

    def _find_marker_root_upward(path: Path) -> Path | None:
        text = str(path.resolve())
        if "/a/" in text:
            return base_root / "a"
        if "/b/" in text:
            return base_root / "b"
        return None

    with pytest.raises(RuntimeError, match="multiple project roots"):
        tmux_core.resolve_project_root_from_panes(
            [str(a), str(b)],
            base_root,
            is_under=_is_under,
            find_marker_root_upward=_find_marker_root_upward,
        )
