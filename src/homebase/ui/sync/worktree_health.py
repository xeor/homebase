from __future__ import annotations

import threading
import time
from typing import Any

from textual.widgets import Static

from ...cache.api import cache_load_worktree_health, cache_save_worktree_health
from ...core.utils import WIDGET_API_ERRORS
from ...workspace.health import audit_workspace

BANNER_ID = "#worktree_health_banner"


def _issue_to_dict(issue) -> dict[str, object]:
    return {
        "kind": issue.kind,
        "path": str(issue.path),
        "detail": issue.detail,
        "fix_summary": issue.fix_summary,
        "parent_path": str(issue.parent_path) if issue.parent_path else "",
    }


def load_initial_health(app: Any) -> None:
    cached = cache_load_worktree_health(app.base_dir)
    if cached is None:
        app.worktree_health_issues = []
        app.worktree_health_last_scan_ts = 0
        _paint_banner(app)
        return
    scan_at, issues = cached
    app.worktree_health_issues = list(issues)
    app.worktree_health_last_scan_ts = int(scan_at)
    if issues and not getattr(app, "worktree_health_dismissed", False):
        _announce(app, issues)
    _paint_banner(app)


def maybe_refresh_worktree_health(app: Any, *, interval_s: float) -> None:
    if getattr(app, "fast_exit_requested", False):
        return
    if getattr(app, "worktree_health_refresh_running", False):
        return
    now = time.time()
    last = float(getattr(app, "worktree_health_refresh_last_ts", 0.0))
    if now - last < interval_s:
        return

    app.worktree_health_refresh_running = True
    app.worktree_health_refresh_last_ts = now
    base_dir = app.base_dir

    def worker() -> None:
        try:
            raw_issues = audit_workspace(base_dir)
        except (OSError, ValueError):
            raw_issues = []
        payload = [_issue_to_dict(issue) for issue in raw_issues]
        scan_at = int(time.time())
        cache_save_worktree_health(base_dir, scan_at, payload)
        app.call_from_thread(on_worktree_health_refresh_done, app, payload, scan_at)

    threading.Thread(target=worker, daemon=True).start()


def on_worktree_health_refresh_done(
    app: Any, issues: list[dict[str, object]], scan_at: int
) -> None:
    app.worktree_health_refresh_running = False
    prev = list(app.worktree_health_issues or [])
    app.worktree_health_issues = list(issues)
    app.worktree_health_last_scan_ts = int(scan_at)
    count_changed = len(prev) != len(issues)
    if count_changed:
        app.worktree_health_dismissed = False
    if not issues:
        if prev:
            app._log("worktree health: clean", "info")
        _paint_banner(app)
        return
    if getattr(app, "worktree_health_dismissed", False) and not count_changed:
        _paint_banner(app)
        return
    _announce(app, issues)
    _paint_banner(app)


def dismiss_worktree_health(app: Any) -> None:
    app.worktree_health_dismissed = True
    _paint_banner(app)


def _paint_banner(app: Any) -> None:
    try:
        banner = app.query_one(BANNER_ID, Static)
    except WIDGET_API_ERRORS:
        return
    issues = list(getattr(app, "worktree_health_issues", []) or [])
    dismissed = bool(getattr(app, "worktree_health_dismissed", False))
    if not issues or dismissed:
        banner.update("")
        banner.remove_class("visible")
        return
    kinds: dict[str, int] = {}
    for issue in issues:
        key = str(issue.get("kind", "unknown"))
        kinds[key] = kinds.get(key, 0) + 1
    breakdown = ", ".join(f"{k}:{n}" for k, n in sorted(kinds.items()))
    banner.update(
        f"⚠ worktree health: {len(issues)} issue(s) [{breakdown}] — "
        f"run 'b fix-worktrees --apply'  ·  ctrl+x to dismiss"
    )
    banner.add_class("visible")


def _announce(app: Any, issues: list[dict[str, object]]) -> None:
    kinds: dict[str, int] = {}
    for issue in issues:
        key = str(issue.get("kind", "unknown"))
        kinds[key] = kinds.get(key, 0) + 1
    breakdown = ", ".join(f"{kind}:{count}" for kind, count in sorted(kinds.items()))
    msg = (
        f"worktree health: {len(issues)} issue(s) [{breakdown}] — "
        f"run 'b fix-worktrees --apply'"
    )
    app._log(msg, "warn")


__all__ = [
    "load_initial_health",
    "maybe_refresh_worktree_health",
    "on_worktree_health_refresh_done",
    "dismiss_worktree_health",
    "BANNER_ID",
]
