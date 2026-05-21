from __future__ import annotations

from pathlib import Path

from homebase.core.models import ProjectRow
from homebase.workspace.filter_compile import compile_filter_expr


def _row(name: str, *, worktree_of: str = "") -> ProjectRow:
    return ProjectRow(
        path=Path(f"/tmp/{name}"),
        name=name,
        branch="main",
        dirty="",
        last="-",
        src="fs",
        created="-",
        tags=[],
        properties=[],
        description="",
        created_ts=0,
        last_ts=0,
        git_ts=0,
        opened_ts=0,
        is_fork=False,
        is_tmp=False,
        archived=False,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
        worktree_of=worktree_of,
    )


_ROWS = [
    _row("foo"),
    _row("foo-featx", worktree_of="foo"),
    _row("foo-bug", worktree_of="foo"),
    _row("bar"),
]


def _matches(expr: str) -> list[str]:
    pred, _err = compile_filter_expr(expr)
    return [r.name for r in _ROWS if pred(r)]


def test_repo_matches_parent_and_all_worktrees() -> None:
    assert _matches(":repo=foo") == ["foo", "foo-featx", "foo-bug"]


def test_repo_excludes_unrelated_rows() -> None:
    assert _matches(":repo=bar") == ["bar"]


def test_worktree_of_excludes_parent() -> None:
    assert _matches(":worktree-of=foo") == ["foo-featx", "foo-bug"]


def test_worktree_of_matches_nothing_when_parent_has_no_worktrees() -> None:
    assert _matches(":worktree-of=bar") == []


def test_worktree_filter_non_equal_emits_hint() -> None:
    pred, err = compile_filter_expr(":repo!=foo")
    assert err is not None
    assert "not implemented" in err
    assert not any(pred(r) for r in _ROWS)
