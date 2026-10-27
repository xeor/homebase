"""Incremental worktree-health sweep shared by the TUI and `b daemon`.

Each audit unit is re-audited only when its input signature changed; the
per-unit results and the aggregate live in the cache."""
from __future__ import annotations

import time
from pathlib import Path

from ..cache.api import (
    cache_load_worktree_health_rows,
    cache_prune_worktree_health_rows,
    cache_save_worktree_health,
    cache_upsert_worktree_health_row,
)
from .health import (
    WorktreeIssue,
    audit_unit,
    audit_unit_signature,
    list_audit_units,
)


def issue_to_dict(issue: WorktreeIssue) -> dict[str, object]:
    return {
        "kind": issue.kind,
        "path": str(issue.path),
        "detail": issue.detail,
        "fix_summary": issue.fix_summary,
        "parent_path": str(issue.parent_path) if issue.parent_path else "",
    }


def _refresh_unit(
    base_dir: Path,
    unit_str: str,
    cached: dict[str, tuple[str, int, list[dict[str, object]]]],
    now_scan: int,
) -> bool:
    """Re-audit one unit when its inputs changed. False when it vanished."""
    unit_path = Path(unit_str)
    try:
        sig = audit_unit_signature(base_dir, unit_path)
    except OSError:
        return False
    cached_entry = cached.get(unit_str)
    if cached_entry is not None and cached_entry[0] == sig:
        return True
    try:
        issues = audit_unit(base_dir, unit_path)
    except (OSError, ValueError):
        issues = []
    payload = [issue_to_dict(issue) for issue in issues]
    cache_upsert_worktree_health_row(base_dir, unit_str, sig, now_scan, payload)
    cached[unit_str] = (sig, now_scan, payload)
    return True


def scan_worktree_health(
    base_dir: Path,
    cursor: list[str],
    *,
    budget_s: float | None,
) -> tuple[list[dict[str, object]], list[str], int, int]:
    """Continue a sweep from ``cursor`` (an empty cursor starts a new one).

    Stops after ``budget_s`` seconds (None = finish the sweep) and stores
    the aggregate. Returns (issues, remaining cursor, units visited,
    scan time)."""
    remaining = list(cursor)
    if not remaining:
        remaining = [str(unit) for unit in list_audit_units(base_dir)]
        # Drop cache entries for paths that vanished.
        cache_prune_worktree_health_rows(base_dir, set(remaining))
    cached = cache_load_worktree_health_rows(base_dir)
    deadline = None if budget_s is None else time.monotonic() + budget_s
    now_scan = int(time.time())
    visited = 0
    while remaining:
        if _refresh_unit(base_dir, remaining.pop(0), cached, now_scan):
            visited += 1
        if deadline is not None and time.monotonic() >= deadline:
            break
    aggregate: list[dict[str, object]] = []
    for _path, (_sig, _ts, entries) in cached.items():
        aggregate.extend(entries)
    cache_save_worktree_health(base_dir, now_scan, aggregate)
    return aggregate, remaining, visited, now_scan
