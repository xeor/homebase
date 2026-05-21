from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..metadata.api import (
    append_base_log,
    clear_base_worktree,
    load_base_worktree,
)


def deworktree(base_dir: Path, target: Path) -> None:
    block = load_base_worktree(target)
    if block is None:
        raise ValueError(f"not a worktree project: {target}")
    parent_path_str = block.get("parent_path")
    if not parent_path_str:
        raise ValueError(f"missing worktree.parent_path: {target}")
    gitdir_id = block.get("gitdir_id")
    if not gitdir_id:
        raise ValueError(f"missing worktree.gitdir_id: {target}")
    parent_repo = Path(parent_path_str)
    parent_git = parent_repo / ".git"
    if not parent_git.is_dir():
        raise ValueError(f"parent .git missing or not a directory: {parent_git}")
    worktree_repo = target / "repo"
    if not worktree_repo.is_dir():
        raise ValueError(f"worktree repo missing: {worktree_repo}")
    parent_admin = parent_git / "worktrees" / gitdir_id
    if not parent_admin.is_dir():
        raise ValueError(f"parent admin entry missing: {parent_admin}")

    branch = block["branch"]
    new_git_tmp = worktree_repo / ".git_new"
    if new_git_tmp.exists():
        shutil.rmtree(new_git_tmp)

    shutil.copytree(parent_git, new_git_tmp, symlinks=True)
    wt_subdir = new_git_tmp / "worktrees"
    if wt_subdir.exists():
        shutil.rmtree(wt_subdir)

    for name in ("HEAD", "index", "ORIG_HEAD", "FETCH_HEAD", "MERGE_HEAD", "logs"):
        src = parent_admin / name
        if not src.exists():
            continue
        dst = new_git_tmp / name
        if dst.exists():
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        if src.is_dir():
            shutil.copytree(src, dst, symlinks=True)
        else:
            shutil.copy2(src, dst)

    git_pointer = worktree_repo / ".git"
    if git_pointer.exists() or git_pointer.is_symlink():
        if git_pointer.is_file() or git_pointer.is_symlink():
            git_pointer.unlink()
        else:
            shutil.rmtree(git_pointer)
    new_git_tmp.rename(git_pointer)

    try:
        subprocess.run(
            ["git", "-C", str(worktree_repo), "symbolic-ref", "HEAD", f"refs/heads/{branch}"],
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, OSError) as exc:
        raise ValueError(f"failed to set HEAD to {branch}: {exc}") from exc

    shutil.rmtree(parent_admin)
    clear_base_worktree(target)
    append_base_log(
        target,
        "deworktree",
        {"former_parent": block["of"], "branch": branch},
    )


__all__ = ["deworktree"]
