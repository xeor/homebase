"""Git fixture helpers shared by the demo/example and benchmark
seeders. Each helper is opinion-free about layout — the caller picks
where the repo lives and what it contains."""
from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path


def git_init(
    repo: Path,
    *,
    user_email: str = "seed@example.local",
    user_name: str = "seed",
    initial_branch: str = "main",
) -> None:
    """``git init`` at ``repo`` (created if missing), with the local
    user config + gpg signing disabled. Idempotent on the dir but not
    on the git state — call once per repo."""
    repo.mkdir(parents=True, exist_ok=True)
    _run(["git", "-C", str(repo), "init", "-q", "-b", initial_branch])
    _run(["git", "-C", str(repo), "config", "user.email", user_email])
    _run(["git", "-C", str(repo), "config", "user.name", user_name])
    _run(["git", "-C", str(repo), "config", "commit.gpgsign", "false"])


def commit_files(
    repo: Path,
    message: str,
    *,
    author_date: datetime | None = None,
    paths: Sequence[str] | None = None,
) -> None:
    """Stage ``paths`` (or everything if ``None``) and commit. If
    ``author_date`` is given, both ``GIT_AUTHOR_DATE`` and
    ``GIT_COMMITTER_DATE`` are set so the commit lands at that
    timestamp — needed for fixtures with believable git history."""
    env = os.environ.copy()
    if author_date is not None:
        iso = _iso_z(author_date)
        env["GIT_AUTHOR_DATE"] = iso
        env["GIT_COMMITTER_DATE"] = iso
    add_args = ["git", "-C", str(repo), "add"]
    if paths:
        add_args.extend(str(p) for p in paths)
    else:
        add_args.append(".")
    _run(add_args, env=env)
    _run(["git", "-C", str(repo), "commit", "-q", "-m", message], env=env)


def read_gitdir_id(parent_repo: Path, worktree_repo: Path) -> str:
    """Locate the parent's ``.git/worktrees/<id>/`` entry that points
    at ``worktree_repo``. Raises ``ValueError`` if no entry matches —
    that's a programmer error (the worktree wasn't actually added)."""
    admin = parent_repo / ".git" / "worktrees"
    if not admin.is_dir():
        raise ValueError(f"parent repo has no worktrees admin dir: {admin}")
    target_str = str(worktree_repo.resolve())
    for entry in admin.iterdir():
        gitdir_file = entry / "gitdir"
        if not gitdir_file.is_file():
            continue
        try:
            text = gitdir_file.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not text:
            continue
        pointed = Path(text)
        if pointed.name == ".git":
            pointed = pointed.parent
        if str(pointed.resolve()) == target_str:
            return entry.name
    raise ValueError(f"could not locate gitdir_id for {worktree_repo}")


def _iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _run(cmd: list[str], *, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, check=True, env=env, capture_output=True)


__all__ = [
    "commit_files",
    "git_init",
    "read_gitdir_id",
]
