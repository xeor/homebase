from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ....cache.api import cache_upsert_project_fast
from ....metadata.api import (
    append_base_log,
    ensure_base_marker,
    load_base_repo_dir,
    load_base_worktree,
    save_base_repo_dir,
    save_base_tags,
    save_base_worktree,
)
from ..base import NewContext, NewOptions, NewPlan, NewResult, Source
from ..registry import register_source


def sanitize_branch_for_dir(branch: str) -> str:
    return branch.replace("/", "--")


def resolve_root_parent(base_dir: Path, name: str) -> tuple[Path, str]:
    """Walk worktree.of chain from a project name until we hit a
    non-worktree. Returns (root_path, root_name)."""
    seen: set[str] = set()
    current = name
    while True:
        if current in seen:
            raise ValueError(f"worktree.of cycle through {current!r}")
        seen.add(current)
        path = base_dir / current
        if not path.is_dir():
            raise ValueError(f"parent project not found: {current}")
        block = load_base_worktree(path)
        if block is None:
            return path, current
        current = block["of"]


def _read_gitdir_id(parent_repo: Path, worktree_repo: Path) -> str:
    admin = parent_repo / ".git" / "worktrees"
    if not admin.is_dir():
        raise ValueError(f"parent repo has no worktrees admin dir: {admin}")
    target_str = str(worktree_repo.resolve())
    for entry in admin.iterdir():
        gitdir_file = entry / "gitdir"
        if not gitdir_file.is_file():
            continue
        try:
            text = gitdir_file.read_text(encoding="utf-8", errors="replace").strip()
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


def _current_branch(repo: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise ValueError(f"git branch --show-current failed in {repo}: {exc}") from exc
    branch = proc.stdout.strip()
    return branch or None


def _branch_exists(repo: Path, branch: str) -> bool:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return proc.returncode == 0


@register_source
class WorktreeSource(Source):
    key = "worktree"
    help_short = "Create a project as a git worktree of an existing project."
    default_options = {}
    default_config = {}

    def detects(self, raw_input, ctx: NewContext) -> bool:
        return False

    def infer_name(self, raw_input, ctx: NewContext) -> str | None:
        if not raw_input:
            return None
        return sanitize_branch_for_dir(str(raw_input))

    def plan(
        self,
        raw_input,
        name: str,
        options: NewOptions,
        ctx: NewContext,
    ) -> NewPlan:
        if not raw_input:
            raise ValueError("worktree source requires a branch name")
        if not options.from_project:
            raise ValueError("worktree source requires --from <parent-project>")
        branch = str(raw_input).strip()
        if not branch:
            raise ValueError("worktree branch name is empty")

        root_path, root_name = resolve_root_parent(ctx.base_dir, options.from_project)
        root_repo_dir = load_base_repo_dir(root_path)
        if not root_repo_dir:
            raise ValueError(
                f"parent {root_name} has no repo_dir configured — run "
                f"`b fix --repo-dir` first"
            )
        root_repo = root_path / root_repo_dir
        if not (root_repo / ".git").exists():
            raise ValueError(f"parent has no git repo at: {root_repo}")

        sanitized = sanitize_branch_for_dir(branch)
        dir_name = f"{root_name}-{sanitized}"
        target = ctx.base_dir / dir_name
        if target.exists():
            raise ValueError(f"target already exists: {target}")

        base_ref = _resolve_base_ref(ctx.cwd, root_repo)
        branch_already_exists = _branch_exists(root_repo, branch)

        steps = [
            f"mkdir {target}",
            (
                f"git worktree add {target}/repo {branch}"
                if branch_already_exists
                else f"git worktree add -b {branch} {target}/repo {base_ref or 'HEAD'}"
            ),
            f"write {target}/.base.yaml",
        ]
        if options.tags:
            steps.append(f"set tags {list(options.tags)}")

        return NewPlan(
            source_key=self.key,
            name=dir_name,
            target=target,
            steps=steps,
            tags=list(options.tags),
            template="",
            post_commands=list(options.post),
            log_kind="creation",
            log_payload={
                "kind": "worktree",
                "of": root_name,
                "branch": branch,
                "parent_path": str(root_repo),
                "base_ref": base_ref or "",
                "branch_existed": branch_already_exists,
            },
            input=raw_input,
            open_shell=options.open,
        )

    def apply(self, plan: NewPlan, ctx: NewContext) -> NewResult:
        target = plan.target
        if target.exists():
            raise ValueError(f"target already exists: {target}")

        payload = plan.log_payload
        root_name = str(payload["of"])
        branch = str(payload["branch"])
        root_repo = Path(str(payload["parent_path"]))
        base_ref = str(payload.get("base_ref") or "")
        branch_existed = bool(payload.get("branch_existed", False))
        worktree_repo = target / "repo"

        target.mkdir(parents=True)
        try:
            args = ["git", "-C", str(root_repo), "worktree", "add"]
            if branch_existed:
                args += [str(worktree_repo), branch]
            else:
                args += ["-b", branch, str(worktree_repo)]
                if base_ref:
                    args.append(base_ref)
            proc = subprocess.run(args, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "").strip()
                raise ValueError(f"git worktree add failed: {detail}")

            gitdir_id = _read_gitdir_id(root_repo, worktree_repo)
            ensure_base_marker(target)
            # Worktrees always land under <project>/repo/. Write the
            # config explicitly so b fix doesn't have to guess.
            save_base_repo_dir(target, "repo")
            save_base_worktree(
                target,
                of=root_name,
                branch=branch,
                parent_path=str(root_repo),
                gitdir_id=gitdir_id,
            )
            if plan.tags:
                clean = sorted({t.strip() for t in plan.tags if t.strip()})
                if clean:
                    save_base_tags(ctx.base_dir, target, clean)
            append_base_log(target, plan.log_kind, plan.log_payload)
        except (OSError, ValueError, subprocess.SubprocessError):
            _abort_worktree(root_repo, worktree_repo)
            shutil.rmtree(target, ignore_errors=True)
            raise

        cache_upsert_project_fast(ctx.base_dir, target)
        return NewResult(target=target, open_shell=plan.open_shell)


def _resolve_base_ref(cwd: Path, root_repo: Path) -> str | None:
    enclosing_repo = _enclosing_git_repo(cwd)
    if enclosing_repo is None:
        enclosing_repo = root_repo
    branch = _current_branch(enclosing_repo)
    if branch:
        return branch
    try:
        proc = subprocess.run(
            ["git", "-C", str(enclosing_repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    sha = proc.stdout.strip()
    return sha or None


def _enclosing_git_repo(cwd: Path) -> Path | None:
    cur = cwd.resolve()
    for ancestor in (cur, *cur.parents):
        if (ancestor / ".git").exists():
            return ancestor
    return None


def _abort_worktree(root_repo: Path, worktree_repo: Path) -> None:
    try:
        subprocess.run(
            ["git", "-C", str(root_repo), "worktree", "remove", "--force", str(worktree_repo)],
            capture_output=True,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return


__all__ = ["WorktreeSource", "resolve_root_parent", "sanitize_branch_for_dir"]
