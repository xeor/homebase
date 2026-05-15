from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable


def cmd_tags_sync(
    base_dir: Path,
    *,
    sync_tag_symlinks_detailed: Callable[[Path, bool, bool], tuple[str | None, list[str]]],
    verbose: bool,
    debug: bool,
) -> int:
    err, lines = sync_tag_symlinks_detailed(base_dir, verbose, debug)
    if verbose:
        for line in lines:
            print(line)
    if err:
        print(f"tag sync failed: {err}", file=sys.stderr)
        return 1
    if not verbose:
        print("tag sync ok")
    return 0


def cmd_status(base_dir: Path, *, collect_projects: Callable[[Path], list[Any]]) -> int:
    print(f"{'PROJECT':<25} {'BRANCH':<15} {'DIRTY':<5} {'MODIFIED':<10} TAGS")
    print(f"{'-------':<25} {'------':<15} {'-----':<5} {'--------':<10} ----")
    for row in collect_projects(base_dir):
        tag_s = ",".join(row.tags)
        print(f"{row.name:<25} {row.branch[:15]:<15} {row.dirty[:1]:<5} {row.last:<10} {tag_s}")
    return 0


def cmd_recent(
    base_dir: Path,
    *,
    collect_projects: Callable[[Path], list[Any]],
    sort_rows: Callable[[list[Any], str], list[Any]],
    fmt_ymd: Callable[[int], str],
) -> int:
    rows = sort_rows(collect_projects(base_dir), "git")
    for row in rows[:20]:
        stamp = fmt_ymd(row.git_ts) if row.git_ts > 0 else row.last
        print(f"{stamp}  {row.name}")
    return 0


def cmd_cd(
    base_dir: Path,
    name: str,
    *,
    archive_dir_name: str,
    open_shell_in_dir: Callable[[Path], int],
) -> int:
    """Spawn a shell in ``<base>/<name>``. Works from anywhere, so the
    user can jump to any project they know the name of without first
    cd-ing into base. Tab completion narrows ``<name>`` to active
    (non-archived) projects.

    Empty ``<name>`` is treated as "drop me into base itself"."""
    target_name = (name or "").strip()
    if not target_name:
        return open_shell_in_dir(base_dir)
    candidate = (base_dir / target_name).resolve()
    base_resolved = base_dir.resolve()
    try:
        rel = candidate.relative_to(base_resolved)
    except ValueError:
        print(f"refusing to cd outside base: {candidate}", file=sys.stderr)
        return 2
    parts = rel.parts
    if not parts:
        # User asked for base itself via something like ``b cd .``.
        return open_shell_in_dir(candidate)
    first = parts[0]
    # ``_archive``, ``_tags``, and any other underscore / dot dir
    # under base is bookkeeping, not a project. Block the jump so
    # ``b cd _archive`` doesn't silently land in the archive root.
    if first.startswith("_") or first.startswith("."):
        print(
            f"refusing to cd into a reserved/hidden dir: {first}",
            file=sys.stderr,
        )
        return 2
    if first == archive_dir_name:
        print(
            f"refusing to cd into the archive (use `b archive ls`): {first}",
            file=sys.stderr,
        )
        return 2
    if not candidate.is_dir():
        print(f"no such project: {target_name}", file=sys.stderr)
        return 2
    return open_shell_in_dir(candidate)
