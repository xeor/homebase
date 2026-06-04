from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from ..metadata.api import (
    append_base_log,
    load_base_repo_dir,
    load_base_worktree,
    save_base_worktree,
)
from .deworktree import deworktree
from .worktree_paths import find_worktree_children


def deworktree_family(base_dir: Path, worktrees: list[Path]) -> list[Path]:
    """De-worktree every entry; return the paths that were processed."""
    done: list[Path] = []
    for wt in worktrees:
        deworktree(base_dir, wt)
        done.append(wt)
    return done


def archive_family_together(
    base_dir: Path,
    parent: Path,
    worktrees: list[Path],
    *,
    archive_move: Callable[[Path, Path], Path],
) -> tuple[Path, list[Path]]:
    """Archive the worktrees first (so the parent's archive preflight
    no longer sees active siblings), then archive the parent, then re-
    anchor every archived worktree's git pointer at the archived parent.
    Returns (archived_parent_path, [archived_worktree_path, ...])."""
    archived_worktrees: list[Path] = []
    for wt in worktrees:
        dst = archive_move(base_dir, wt)
        archived_worktrees.append(dst)
    archived_parent = archive_move(base_dir, parent)
    for archived_wt in archived_worktrees:
        _reanchor_archived_worktree(archived_parent, archived_wt)
    return archived_parent, archived_worktrees


def _reanchor_archived_worktree(archived_parent: Path, archived_wt: Path) -> None:
    parent_repo = archived_parent / (load_base_repo_dir(archived_parent) or "repo")
    worktree_repo = archived_wt / (load_base_repo_dir(archived_wt) or "repo")
    if not parent_repo.is_dir():
        return
    try:
        subprocess.run(
            [
                "git",
                "-C",
                str(parent_repo),
                "worktree",
                "repair",
                str(worktree_repo),
            ],
            capture_output=True,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return
    block = load_base_worktree(archived_wt)
    if block is None:
        return
    save_base_worktree(
        archived_wt,
        of=block["of"],
        branch=block["branch"],
        parent_path=str(parent_repo),
        gitdir_id=block.get("gitdir_id"),
    )
    append_base_log(
        archived_wt,
        "archive_family_reanchor",
        {"archived_parent_repo": str(parent_repo)},
    )


__all__ = [
    "deworktree_family",
    "archive_family_together",
    "find_worktree_children",
]
