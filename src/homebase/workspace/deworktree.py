from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..metadata.api import (
    append_base_log,
    clear_base_worktree,
    load_base_repo_dir,
    load_base_worktree,
)


def _validate_worktree_block(target: Path, block: dict | None) -> dict:
    if block is None:
        raise ValueError(f"not a worktree project: {target}")
    if not block.get("parent_path"):
        raise ValueError(f"missing worktree.parent_path: {target}")
    if not block.get("gitdir_id"):
        raise ValueError(f"missing worktree.gitdir_id: {target}")
    return block


def _resolve_deworktree_paths(target: Path, block: dict) -> tuple[Path, Path, Path]:
    parent_repo = Path(block["parent_path"])
    parent_git = parent_repo / ".git"
    if not parent_git.is_dir():
        raise ValueError(
            f"parent .git missing or not a directory: {parent_git}"
        )
    worktree_repo_dir = load_base_repo_dir(target) or "repo"
    worktree_repo = target / worktree_repo_dir
    if not worktree_repo.is_dir():
        raise ValueError(f"worktree repo missing: {worktree_repo}")
    parent_admin = parent_git / "worktrees" / block["gitdir_id"]
    if not parent_admin.is_dir():
        raise ValueError(f"parent admin entry missing: {parent_admin}")
    return parent_git, worktree_repo, parent_admin


def _copy_parent_admin_entries(parent_admin: Path, new_git_tmp: Path) -> None:
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


def _replace_git_pointer(worktree_repo: Path, new_git_tmp: Path) -> None:
    git_pointer = worktree_repo / ".git"
    if git_pointer.exists() or git_pointer.is_symlink():
        if git_pointer.is_file() or git_pointer.is_symlink():
            git_pointer.unlink()
        else:
            shutil.rmtree(git_pointer)
    new_git_tmp.rename(git_pointer)


def _build_new_git_dir(
    parent_git: Path, parent_admin: Path, worktree_repo: Path
) -> Path:
    new_git_tmp = worktree_repo / ".git_new"
    if new_git_tmp.exists():
        shutil.rmtree(new_git_tmp)
    shutil.copytree(parent_git, new_git_tmp, symlinks=True)
    wt_subdir = new_git_tmp / "worktrees"
    if wt_subdir.exists():
        shutil.rmtree(wt_subdir)
    _copy_parent_admin_entries(parent_admin, new_git_tmp)
    return new_git_tmp


def deworktree(base_dir: Path, target: Path) -> None:
    block = _validate_worktree_block(target, load_base_worktree(target))
    parent_git, worktree_repo, parent_admin = _resolve_deworktree_paths(target, block)
    branch = block["branch"]
    new_git_tmp = _build_new_git_dir(parent_git, parent_admin, worktree_repo)
    _replace_git_pointer(worktree_repo, new_git_tmp)
    try:
        subprocess.run(
            [
                "git",
                "-C",
                str(worktree_repo),
                "symbolic-ref",
                "HEAD",
                f"refs/heads/{branch}",
            ],
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
