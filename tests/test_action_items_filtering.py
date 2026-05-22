from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from homebase.core.models import ProjectRow
from homebase.ui.actions.action_items import valid_action_items


def _row(
    path: Path,
    *,
    name: str | None = None,
    archived: bool = False,
    worktree_of: str = "",
    repo_dir: str = "",
) -> ProjectRow:
    return ProjectRow(
        path=path,
        name=name or path.name,
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
        archived=archived,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
        worktree_of=worktree_of,
        repo_dir=repo_dir,
    )


def _make_app(rows: list[ProjectRow], *, view_mode: str = "active") -> SimpleNamespace:
    app = SimpleNamespace(
        ctx=SimpleNamespace(actions={}),
        view_mode=view_mode,
        view_config={
            "active": {
                "actions": [
                    ("new_worktree", "New worktree"),
                    ("deworktree", "De-worktree"),
                    ("fix_worktrees", "Fix worktree health"),
                    ("archive", "archive target"),
                    ("set_desc", "set description on target"),
                    ("delete", "delete target"),
                ]
            },
            "archive": {"actions": []},
        },
        active_rows=rows,
        archived_rows=[],
        _readme_button_actions=lambda: [],
        _notes_button_actions=lambda: [],
        _target_rows=lambda: rows,
        _preflight_bulk_action=lambda _action, paths: (paths, []),
        custom_hotkeys=[],
        _esc=lambda x: x,
        _resolve_notes_path_for_row=lambda _r: Path("/tmp/none.md"),
    )
    return app


def _ids(items: list[tuple[str, str]]) -> set[str]:
    return {aid for aid, _label in items}


def test_deworktree_hidden_when_target_is_not_a_worktree(tmp_path: Path) -> None:
    row = _row(tmp_path / "foo", repo_dir="repo")
    (row.path / "repo").mkdir(parents=True)
    (row.path / "repo" / ".git").mkdir()
    app = _make_app([row])
    items = valid_action_items(
        app, color_accent_hex="#fff", base_meta_issues=lambda _p: []
    )
    assert "deworktree" not in _ids(items)


def test_deworktree_shown_when_target_is_a_worktree(tmp_path: Path) -> None:
    row = _row(tmp_path / "foo-featx", worktree_of="foo", repo_dir="repo")
    (row.path / "repo").mkdir(parents=True)
    (row.path / "repo" / ".git").write_text("gitdir: somewhere", encoding="utf-8")
    app = _make_app([row])
    items = valid_action_items(
        app, color_accent_hex="#fff", base_meta_issues=lambda _p: []
    )
    assert "deworktree" in _ids(items)


def test_new_worktree_hidden_when_target_has_no_repo_dir(tmp_path: Path) -> None:
    row = _row(tmp_path / "noproj", repo_dir="")
    app = _make_app([row])
    items = valid_action_items(
        app, color_accent_hex="#fff", base_meta_issues=lambda _p: []
    )
    assert "new_worktree" not in _ids(items)


def test_new_worktree_hidden_when_target_repo_dir_has_no_git(tmp_path: Path) -> None:
    row = _row(tmp_path / "foo", repo_dir="repo")
    (row.path / "repo").mkdir(parents=True)
    # repo_dir is set but the actual .git is missing
    app = _make_app([row])
    items = valid_action_items(
        app, color_accent_hex="#fff", base_meta_issues=lambda _p: []
    )
    assert "new_worktree" not in _ids(items)


def test_new_worktree_shown_when_target_has_git_repo(tmp_path: Path) -> None:
    row = _row(tmp_path / "foo", repo_dir="repo")
    (row.path / "repo").mkdir(parents=True)
    (row.path / "repo" / ".git").mkdir()
    app = _make_app([row])
    items = valid_action_items(
        app, color_accent_hex="#fff", base_meta_issues=lambda _p: []
    )
    assert "new_worktree" in _ids(items)


def test_new_worktree_hidden_with_multi_target(tmp_path: Path) -> None:
    rows = [
        _row(tmp_path / "foo", repo_dir="repo"),
        _row(tmp_path / "bar", repo_dir="repo"),
    ]
    for r in rows:
        (r.path / "repo").mkdir(parents=True)
        (r.path / "repo" / ".git").mkdir()
    app = _make_app(rows)
    items = valid_action_items(
        app, color_accent_hex="#fff", base_meta_issues=lambda _p: []
    )
    assert "new_worktree" not in _ids(items)


def test_new_worktree_hidden_when_target_is_archived(tmp_path: Path) -> None:
    row = _row(tmp_path / "foo", archived=True, repo_dir="repo")
    (row.path / "repo").mkdir(parents=True)
    (row.path / "repo" / ".git").mkdir()
    app = _make_app([row])
    items = valid_action_items(
        app, color_accent_hex="#fff", base_meta_issues=lambda _p: []
    )
    assert "new_worktree" not in _ids(items)


def test_fix_worktrees_shown_even_without_targets(tmp_path: Path) -> None:
    app = _make_app([])
    items = valid_action_items(
        app, color_accent_hex="#fff", base_meta_issues=lambda _p: []
    )
    # Workspace-scope action; available regardless of selection.
    assert "fix_worktrees" in _ids(items)


def test_target_actions_hidden_without_targets(tmp_path: Path) -> None:
    app = _make_app([])
    items = valid_action_items(
        app, color_accent_hex="#fff", base_meta_issues=lambda _p: []
    )
    ids = _ids(items)
    # Target-scope actions stay out when there's no selection.
    assert "deworktree" not in ids
    assert "new_worktree" not in ids
    assert "archive" not in ids
    assert "delete" not in ids
    assert "set_desc" not in ids


def test_deworktree_visible_when_at_least_one_target_is_worktree(tmp_path: Path) -> None:
    parent = _row(tmp_path / "foo", repo_dir="repo")
    (parent.path / "repo").mkdir(parents=True)
    (parent.path / "repo" / ".git").mkdir()
    wt = _row(tmp_path / "foo-featx", worktree_of="foo", repo_dir="repo")
    (wt.path / "repo").mkdir(parents=True)
    (wt.path / "repo" / ".git").write_text("gitdir: x", encoding="utf-8")
    app = _make_app([parent, wt])
    items = valid_action_items(
        app, color_accent_hex="#fff", base_meta_issues=lambda _p: []
    )
    # Mixed selection: parent + worktree → deworktree still appears
    # because the action handler will filter to just the worktree
    # row at execution time (see pick_actions._handle_deworktree).
    assert "deworktree" in _ids(items)


def _init_real_git(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)
    (repo / "f.txt").write_text("a\n", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)


def test_new_worktree_accepts_flat_repo_dir_setting(tmp_path: Path) -> None:
    # A project that explicitly sets repo_dir: '.' (flat layout)
    # should still surface new_worktree.
    proj = tmp_path / "flat"
    _init_real_git(proj)
    row = _row(proj, repo_dir=".")
    app = _make_app([row])
    items = valid_action_items(
        app, color_accent_hex="#fff", base_meta_issues=lambda _p: []
    )
    assert "new_worktree" in _ids(items)
