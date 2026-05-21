from __future__ import annotations

import subprocess
from pathlib import Path

from ..metadata.api import load_base_worktree, save_base_worktree


def move_project(base_dir: Path, old: Path, new: Path) -> None:
    """Move/rename a project directory, keeping worktree pointers correct.

    Worktree row: relies on ``git worktree repair`` after the rename
    to rewrite the parent's ``.git/worktrees/<id>/gitdir`` back at
    the new path. Parent row: also reaches into every child
    ``.base.yaml`` and rewrites ``worktree.of`` / ``worktree.parent_path``.
    """
    if old == new:
        return
    block = load_base_worktree(old)
    children: list[Path] = [] if block is not None else find_worktree_children(base_dir, old.name)

    old.rename(new)

    if block is not None:
        _repair_worktree_pointers(new / "repo")
        _rewrite_worktree_meta(new)
        return
    if children:
        _repair_worktree_pointers(new / "repo")
        new_parent_repo = new / "repo"
        for child in children:
            _rewrite_child_meta(
                child,
                new_parent_name=new.name,
                new_parent_path=str(new_parent_repo),
            )


def repair_after_move(base_dir: Path, new_path: Path) -> None:
    """Re-anchor worktree pointers after a project at ``new_path``
    has just been moved/renamed. Safe to call on plain projects (no-op)."""
    block = load_base_worktree(new_path)
    if block is not None:
        _repair_worktree_pointers(new_path / "repo")
        _rewrite_worktree_meta(new_path)
        return
    children = find_worktree_children(base_dir, new_path.name)
    if children:
        _repair_worktree_pointers(new_path / "repo")
        new_parent_repo = new_path / "repo"
        for child in children:
            _rewrite_child_meta(
                child,
                new_parent_name=new_path.name,
                new_parent_path=str(new_parent_repo),
            )


def find_worktree_children(base_dir: Path, parent_name: str) -> list[Path]:
    if not base_dir.is_dir() or not parent_name:
        return []
    out: list[Path] = []
    for entry in sorted(base_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        if entry.name.startswith(".") or entry.name in {"_archive", "_tags"}:
            continue
        block = load_base_worktree(entry)
        if block is None:
            continue
        if block.get("of") == parent_name:
            out.append(entry)
    return out


def _repair_worktree_pointers(repo: Path) -> None:
    if not repo.exists():
        return
    try:
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "repair"],
            capture_output=True,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return


def _rewrite_worktree_meta(worktree_dir: Path) -> None:
    block = load_base_worktree(worktree_dir)
    if block is None:
        return
    parent_path = block.get("parent_path", "")
    save_base_worktree(
        worktree_dir,
        of=block["of"],
        branch=block["branch"],
        parent_path=parent_path or None,
        gitdir_id=block.get("gitdir_id"),
    )


def _rewrite_child_meta(child: Path, *, new_parent_name: str, new_parent_path: str) -> None:
    block = load_base_worktree(child)
    if block is None:
        return
    save_base_worktree(
        child,
        of=new_parent_name,
        branch=block["branch"],
        parent_path=new_parent_path,
        gitdir_id=block.get("gitdir_id"),
    )


__all__ = ["move_project", "find_worktree_children", "repair_after_move"]
