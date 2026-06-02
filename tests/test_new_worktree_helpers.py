"""Unit tests for the pure helpers exposed by
``workspace/new/sources/worktree.py``."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from homebase.metadata.api import save_base_worktree
from homebase.workspace.new.sources import worktree as wt

# ---- sanitize_branch_for_dir ----------------------------------------


def test_sanitize_branch_for_dir_replaces_slashes() -> None:
    assert wt.sanitize_branch_for_dir("feature/auth") == "feature--auth"
    assert wt.sanitize_branch_for_dir("a/b/c") == "a--b--c"


def test_sanitize_branch_for_dir_keeps_simple_names() -> None:
    assert wt.sanitize_branch_for_dir("main") == "main"
    assert wt.sanitize_branch_for_dir("") == ""


# ---- resolve_root_parent --------------------------------------------


def test_resolve_root_parent_returns_self_for_non_worktree(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".base.yaml").write_text("tags: []\n")
    path, name = wt.resolve_root_parent(tmp_path, "proj")
    assert (path, name) == (proj, "proj")


def test_resolve_root_parent_walks_to_root(tmp_path: Path) -> None:
    """A chain ``c -> b -> a`` must resolve to ``a`` (the non-worktree)."""
    root = tmp_path / "root"
    root.mkdir()
    (root / ".base.yaml").write_text("tags: []\n")
    mid = tmp_path / "mid"
    mid.mkdir()
    save_base_worktree(mid, of="root", branch="main")
    leaf = tmp_path / "leaf"
    leaf.mkdir()
    save_base_worktree(leaf, of="mid", branch="feature")
    path, name = wt.resolve_root_parent(tmp_path, "leaf")
    assert (path, name) == (root, "root")


def test_resolve_root_parent_raises_on_cycle(tmp_path: Path) -> None:
    """A pathological ``a -> b -> a`` cycle must be detected so the
    walk can't spin forever."""
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    save_base_worktree(a, of="b", branch="main")
    save_base_worktree(b, of="a", branch="main")
    with pytest.raises(ValueError, match="cycle"):
        wt.resolve_root_parent(tmp_path, "a")


def test_resolve_root_parent_raises_when_parent_missing(tmp_path: Path) -> None:
    leaf = tmp_path / "leaf"
    leaf.mkdir()
    save_base_worktree(leaf, of="ghost", branch="main")
    with pytest.raises(ValueError, match="parent project not found"):
        wt.resolve_root_parent(tmp_path, "leaf")


# ---- _read_gitdir_id ------------------------------------------------


def test_read_gitdir_id_raises_when_admin_dir_missing(tmp_path: Path) -> None:
    parent_repo = tmp_path / "parent"
    parent_repo.mkdir()
    (parent_repo / ".git").mkdir()  # bare ``.git`` without a ``worktrees`` admin dir
    worktree_repo = tmp_path / "wt"
    worktree_repo.mkdir()
    with pytest.raises(ValueError, match="no worktrees admin dir"):
        wt._read_gitdir_id(parent_repo, worktree_repo)


def test_read_gitdir_id_finds_matching_entry(tmp_path: Path) -> None:
    """The function reads each ``gitdir`` pointer and returns the
    admin-dir entry name whose target resolves to the worktree."""
    parent = tmp_path / "parent"
    admin = parent / ".git" / "worktrees" / "wt-entry"
    admin.mkdir(parents=True)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    # ``gitdir`` typically points at ``<worktree>/.git``; the helper
    # strips the trailing ``.git`` before comparing.
    (admin / "gitdir").write_text(str(worktree / ".git") + "\n", encoding="utf-8")
    assert wt._read_gitdir_id(parent, worktree) == "wt-entry"


def test_read_gitdir_id_supports_direct_directory_pointer(tmp_path: Path) -> None:
    """Some setups point at the worktree dir itself (no trailing
    ``.git``); the helper must handle that path too."""
    parent = tmp_path / "parent"
    admin = parent / ".git" / "worktrees" / "wt-entry"
    admin.mkdir(parents=True)
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (admin / "gitdir").write_text(str(worktree) + "\n", encoding="utf-8")
    assert wt._read_gitdir_id(parent, worktree) == "wt-entry"


def test_read_gitdir_id_skips_entries_without_gitdir_file(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    admin = parent / ".git" / "worktrees"
    admin.mkdir(parents=True)
    # Stray entry without ``gitdir`` — must not crash.
    (admin / "stale").mkdir()
    matching = admin / "real"
    matching.mkdir()
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (matching / "gitdir").write_text(str(worktree) + "\n", encoding="utf-8")
    assert wt._read_gitdir_id(parent, worktree) == "real"


def test_read_gitdir_id_raises_when_no_match(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    admin = parent / ".git" / "worktrees" / "other"
    admin.mkdir(parents=True)
    (admin / "gitdir").write_text("/totally/different/path\n", encoding="utf-8")
    worktree = tmp_path / "wt"
    worktree.mkdir()
    with pytest.raises(ValueError, match="could not locate gitdir_id"):
        wt._read_gitdir_id(parent, worktree)


# ---- _current_branch ------------------------------------------------


def _proc(returncode: int, stdout: str = "", stderr: str = ""):
    class _P:
        def __init__(self) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr
    return _P()


def test_current_branch_returns_stripped_branch(monkeypatch, tmp_path: Path) -> None:
    def fake_run(_cmd, **_kwargs):
        return _proc(0, "main\n")

    monkeypatch.setattr(wt.subprocess, "run", fake_run)
    assert wt._current_branch(tmp_path) == "main"


def test_current_branch_returns_none_for_detached(monkeypatch, tmp_path: Path) -> None:
    """A detached HEAD has an empty branch — the helper translates
    that into ``None`` so the caller can branch on it explicitly."""
    monkeypatch.setattr(wt.subprocess, "run", lambda *a, **kw: _proc(0, "\n"))
    assert wt._current_branch(tmp_path) is None


def test_current_branch_raises_on_subprocess_error(monkeypatch, tmp_path: Path) -> None:
    def boom(*_a, **_kw):
        raise subprocess.SubprocessError("git missing")

    monkeypatch.setattr(wt.subprocess, "run", boom)
    with pytest.raises(ValueError, match="git branch --show-current failed"):
        wt._current_branch(tmp_path)


# ---- _branch_exists -------------------------------------------------


def test_branch_exists_true_when_show_ref_succeeds(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(wt.subprocess, "run", lambda *a, **kw: _proc(0))
    assert wt._branch_exists(tmp_path, "main") is True


def test_branch_exists_false_when_show_ref_nonzero(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(wt.subprocess, "run", lambda *a, **kw: _proc(1))
    assert wt._branch_exists(tmp_path, "missing") is False


def test_branch_exists_false_on_subprocess_error(monkeypatch, tmp_path: Path) -> None:
    def boom(*_a, **_kw):
        raise OSError("git missing")

    monkeypatch.setattr(wt.subprocess, "run", boom)
    assert wt._branch_exists(tmp_path, "main") is False
