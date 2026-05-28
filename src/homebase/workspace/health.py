from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..metadata.api import (
    append_base_log,
    load_base_repo_dir,
    load_base_worktree,
    save_base_worktree,
)
from .worktree_paths import find_worktree_children


def _project_repo(path: Path) -> Path:
    return path / (load_base_repo_dir(path) or "repo")

ISSUE_STALE_GITDIR = "stale_gitdir"
ISSUE_ORPHAN_ADMIN = "orphan_admin"
ISSUE_MISSING_PARENT = "missing_parent"
ISSUE_RELOCATED_PARENT = "relocated_parent"
ISSUE_MISSING_GITDIR_FILE = "missing_gitdir_file"


@dataclass(frozen=True)
class WorktreeIssue:
    path: Path
    kind: str
    detail: str
    fix_summary: str
    parent_path: Path | None = None
    admin_entry: Path | None = None


def audit_workspace(base_dir: Path) -> list[WorktreeIssue]:
    issues: list[WorktreeIssue] = []
    if not base_dir.is_dir():
        return issues
    worktree_rows = _collect_worktree_rows(base_dir)
    parent_rows = _collect_potential_parents(base_dir)

    for row, block in worktree_rows:
        issues.extend(_audit_worktree_row(base_dir, row, block))
    for parent in parent_rows:
        issues.extend(_audit_parent_admin(base_dir, parent, worktree_rows))
    return issues


def audit_unit_signature(base_dir: Path, unit_path: Path) -> str:
    """Stable signature for a worktree row or parent, keyed off the
    mtimes the audit actually depends on. Used by the cached scan to
    skip units that haven't changed since the last visit."""
    repo_git = _project_repo(unit_path) / ".git"
    mt_repo = _mtime_ns(repo_git)
    block = load_base_worktree(unit_path)
    base_meta = unit_path / ".base.yaml"
    mt_meta = _mtime_ns(base_meta)
    if block is not None:
        parent_path_str = block.get("parent_path", "")
        gitdir_id = block.get("gitdir_id", "")
        if parent_path_str and gitdir_id:
            parent_admin = Path(parent_path_str) / ".git" / "worktrees" / gitdir_id
            mt_admin = _mtime_ns(parent_admin)
            mt_admin_gitdir = _mtime_ns(parent_admin / "gitdir")
        else:
            mt_admin = 0
            mt_admin_gitdir = 0
        return f"wt:{mt_meta}:{mt_repo}:{mt_admin}:{mt_admin_gitdir}"
    admin_root = _project_repo(unit_path) / ".git" / "worktrees"
    mt_admin_dir = _mtime_ns(admin_root)
    admin_entries_sig = "|".join(
        f"{p.name}:{_mtime_ns(p / 'gitdir')}"
        for p in sorted(admin_root.iterdir(), key=lambda x: x.name)
        if p.is_dir()
    ) if admin_root.is_dir() else ""
    return f"parent:{mt_meta}:{mt_repo}:{mt_admin_dir}:{admin_entries_sig}"


def _mtime_ns(path: Path) -> int:
    try:
        return int(path.stat().st_mtime_ns)
    except OSError:
        return 0


def audit_unit(
    base_dir: Path,
    unit_path: Path,
    worktree_rows: list[tuple[Path, dict[str, str]]] | None = None,
) -> list[WorktreeIssue]:
    block = load_base_worktree(unit_path)
    if block is not None:
        return list(_audit_worktree_row(base_dir, unit_path, block))
    rows = worktree_rows if worktree_rows is not None else _collect_worktree_rows(base_dir)
    return list(_audit_parent_admin(base_dir, unit_path, rows))


def list_audit_units(base_dir: Path) -> list[Path]:
    if not base_dir.is_dir():
        return []
    units: list[Path] = []
    seen: set[Path] = set()
    for entry, _block in _collect_worktree_rows(base_dir):
        if entry not in seen:
            units.append(entry)
            seen.add(entry)
    for parent in _collect_potential_parents(base_dir):
        if parent not in seen:
            units.append(parent)
            seen.add(parent)
    return units


def _collect_worktree_rows(base_dir: Path) -> list[tuple[Path, dict[str, str]]]:
    out: list[tuple[Path, dict[str, str]]] = []
    for entry in sorted(base_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_dir() or entry.name.startswith(".") or entry.name in {"_archive", "_tags"}:
            continue
        block = load_base_worktree(entry)
        if block is not None:
            out.append((entry, block))
    return out


def _collect_potential_parents(base_dir: Path) -> list[Path]:
    out: list[Path] = []
    for entry in sorted(base_dir.iterdir(), key=lambda p: p.name):
        if not entry.is_dir() or entry.name.startswith(".") or entry.name in {"_archive", "_tags"}:
            continue
        if (_project_repo(entry) / ".git").is_dir():
            out.append(entry)
    return out


def _audit_worktree_row(
    base_dir: Path,
    worktree: Path,
    block: dict[str, str],
) -> list[WorktreeIssue]:
    issues: list[WorktreeIssue] = []
    pointer_file = _project_repo(worktree) / ".git"
    parent_name = block.get("of", "")
    gitdir_id = block.get("gitdir_id", "")
    parent_path_meta = block.get("parent_path", "")
    inferred_parent = _project_repo(base_dir / parent_name) if parent_name else None

    if inferred_parent is None or not inferred_parent.is_dir():
        if parent_path_meta and Path(parent_path_meta).is_dir():
            issues.append(
                WorktreeIssue(
                    path=worktree,
                    kind=ISSUE_RELOCATED_PARENT,
                    detail=(
                        f"worktree.of={parent_name!r} but {parent_name}/ is missing; "
                        f"parent_path still resolves at {parent_path_meta}"
                    ),
                    fix_summary="repair pointers from parent_path",
                    parent_path=Path(parent_path_meta),
                )
            )
            return issues
        issues.append(
            WorktreeIssue(
                path=worktree,
                kind=ISSUE_MISSING_PARENT,
                detail=f"parent project {parent_name!r} is gone",
                fix_summary="deworktree manually or drop worktree: block",
            )
        )
        return issues

    parent_path = inferred_parent
    if not pointer_file.exists():
        issues.append(
            WorktreeIssue(
                path=worktree,
                kind=ISSUE_MISSING_GITDIR_FILE,
                detail=f"{pointer_file} does not exist",
                fix_summary="rebuild pointer via git worktree repair on parent",
                parent_path=parent_path,
            )
        )
        return issues
    if not pointer_file.is_file():
        return issues

    try:
        text = pointer_file.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        text = ""
    expected_admin = parent_path / ".git" / "worktrees" / gitdir_id if gitdir_id else None
    points_at = None
    if text.startswith("gitdir:"):
        points_at = Path(text.split(":", 1)[1].strip())
    if (
        expected_admin is not None
        and (points_at is None or points_at.resolve(strict=False) != expected_admin.resolve(strict=False))
    ):
        issues.append(
            WorktreeIssue(
                path=worktree,
                kind=ISSUE_STALE_GITDIR,
                detail=(
                    f"pointer={points_at} expected={expected_admin}"
                ),
                fix_summary="re-anchor via git worktree repair on parent",
                parent_path=parent_path,
            )
        )
    elif expected_admin is not None and not expected_admin.is_dir():
        issues.append(
            WorktreeIssue(
                path=worktree,
                kind=ISSUE_MISSING_GITDIR_FILE,
                detail=f"parent admin entry {expected_admin} missing",
                fix_summary="recreate admin entry via git worktree repair",
                parent_path=parent_path,
            )
        )
    return issues


def _audit_parent_admin(
    base_dir: Path,
    parent: Path,
    worktree_rows: list[tuple[Path, dict[str, str]]],
) -> list[WorktreeIssue]:
    issues: list[WorktreeIssue] = []
    admin_root = _project_repo(parent) / ".git" / "worktrees"
    if not admin_root.is_dir():
        return issues
    known = {block.get("gitdir_id", ""): row for row, block in worktree_rows}
    for entry in sorted(admin_root.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        gitdir_file = entry / "gitdir"
        if not gitdir_file.is_file():
            continue
        try:
            target = gitdir_file.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            target = ""
        target_path = Path(target) if target else None
        target_exists = target_path is not None and target_path.exists()
        # The admin entry's gitdir file points at a worktree's
        # repo/.git file. Walk two levels up to find the worktree
        # directory and verify it carries .base.yaml — a bare repo
        # at the same path would otherwise slip the audit.
        worktree_dir = target_path.parent.parent if target_path is not None else None
        has_base_yaml = (
            worktree_dir is not None
            and (worktree_dir / ".base.yaml").is_file()
        )
        worktree_row = known.get(entry.name)
        if target_exists and has_base_yaml:
            continue
        if target_exists and not has_base_yaml:
            issues.append(
                WorktreeIssue(
                    path=worktree_dir if worktree_dir is not None else entry,
                    kind=ISSUE_ORPHAN_ADMIN,
                    detail=(
                        f"admin entry {entry} points at {target_path} but no "
                        ".base.yaml — not a managed homebase worktree"
                    ),
                    fix_summary="drop the admin entry (git prune leaves it because target still exists)",
                    parent_path=_project_repo(parent),
                    admin_entry=entry,
                )
            )
            continue
        if worktree_row is not None:
            issues.append(
                WorktreeIssue(
                    path=worktree_row,
                    kind=ISSUE_STALE_GITDIR,
                    detail=(
                        f"admin entry {entry} still points at {target_path}; row lives at {worktree_row}"
                    ),
                    fix_summary="re-anchor via git worktree repair on parent",
                    parent_path=_project_repo(parent),
                )
            )
        else:
            issues.append(
                WorktreeIssue(
                    path=entry,
                    kind=ISSUE_ORPHAN_ADMIN,
                    detail=f"admin entry at {entry} has no matching row and no live path",
                    fix_summary="prune via git worktree prune",
                    parent_path=_project_repo(parent),
                    admin_entry=entry,
                )
            )
    return issues


def repair_issue(issue: WorktreeIssue) -> tuple[bool, str]:
    if issue.kind in {ISSUE_STALE_GITDIR, ISSUE_MISSING_GITDIR_FILE, ISSUE_RELOCATED_PARENT}:
        return _repair_via_repair(issue)
    if issue.kind == ISSUE_ORPHAN_ADMIN:
        return _repair_via_prune(issue)
    return False, f"no automatic fix for {issue.kind}"


def _repair_via_repair(issue: WorktreeIssue) -> tuple[bool, str]:
    parent_repo = issue.parent_path
    if parent_repo is None:
        return False, "missing parent_path"
    if not parent_repo.is_dir():
        return False, f"parent_path not a directory: {parent_repo}"
    try:
        proc = subprocess.run(
            ["git", "-C", str(parent_repo), "worktree", "repair", str(_project_repo(issue.path))],
            capture_output=True,
            text=True,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return False, f"git worktree repair failed: {exc}"
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return False, f"git worktree repair exit={proc.returncode}: {detail}"
    if issue.kind == ISSUE_RELOCATED_PARENT:
        block = load_base_worktree(issue.path)
        if block is not None:
            save_base_worktree(
                issue.path,
                of=block["of"],
                branch=block["branch"],
                parent_path=str(parent_repo),
                gitdir_id=block.get("gitdir_id"),
            )
    append_base_log(
        issue.path,
        "worktree_repair",
        {"kind": issue.kind, "detail": issue.detail},
    )
    return True, "git worktree repair applied"


def _repair_via_prune(issue: WorktreeIssue) -> tuple[bool, str]:
    parent_repo = issue.parent_path
    if parent_repo is None or not parent_repo.is_dir():
        return False, "parent_path missing"
    admin_entry = issue.admin_entry
    try:
        proc = subprocess.run(
            ["git", "-C", str(parent_repo), "worktree", "prune"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return False, f"git worktree prune failed: {exc}"
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "").strip()

    # `git worktree prune` only deletes admin entries whose target path
    # no longer exists. If the orphan admin still points at a live
    # directory (case A: target exists but isn't a homebase worktree),
    # prune silently leaves it in place. Verify and fall back to a
    # direct removal of the admin entry so we don't lie about success.
    if admin_entry is None:
        return True, "git worktree prune applied"
    if not admin_entry.exists():
        return True, "git worktree prune applied"
    try:
        shutil.rmtree(admin_entry)
    except OSError as exc:
        return (
            False,
            (
                f"git worktree prune left admin entry {admin_entry} in place "
                f"(target path likely still exists); direct removal failed: {exc}"
            ),
        )
    if admin_entry.exists():
        return (
            False,
            f"admin entry {admin_entry} still present after prune and direct removal",
        )
    return True, f"removed orphan admin entry {admin_entry}"


def list_workspace_parents(base_dir: Path) -> list[Path]:
    return _collect_potential_parents(base_dir)


__all__ = [
    "WorktreeIssue",
    "audit_workspace",
    "audit_unit",
    "audit_unit_signature",
    "list_audit_units",
    "repair_issue",
    "find_worktree_children",
    "ISSUE_STALE_GITDIR",
    "ISSUE_ORPHAN_ADMIN",
    "ISSUE_MISSING_PARENT",
    "ISSUE_RELOCATED_PARENT",
    "ISSUE_MISSING_GITDIR_FILE",
]
