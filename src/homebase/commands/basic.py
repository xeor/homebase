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
