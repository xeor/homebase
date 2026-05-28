from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

from textual.widgets import Static

from ...cache.api import (
    cache_load_worktree_health,
    cache_load_worktree_health_rows,
    cache_prune_worktree_health_rows,
    cache_save_worktree_health,
    cache_upsert_worktree_health_row,
)
from ...core.utils import WIDGET_API_ERRORS
from ...workspace.health import (
    audit_unit,
    audit_unit_signature,
    audit_workspace,
    list_audit_units,
    repair_issue,
)

SCAN_BUDGET_S = 0.2

BANNER_ID = "#worktree_health_banner"


def _is_idle(app: Any) -> bool:
    if bool(getattr(app, "query_apply_pending", False)):
        return False
    if int(getattr(app, "_busy_depth", 0)) > 0:
        return False
    critical = getattr(app, "_critical_job_active", None)
    if callable(critical) and critical():
        return False
    return True


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
    if not _is_idle(app):
        return
    now = time.time()
    last = float(getattr(app, "worktree_health_refresh_last_ts", 0.0))
    cursor = list(getattr(app, "worktree_health_scan_cursor", []) or [])
    if not cursor and now - last < interval_s:
        return

    app.worktree_health_refresh_running = True
    app.worktree_health_refresh_last_ts = now
    base_dir = app.base_dir

    def worker() -> None:
        try:
            cur_cursor = list(getattr(app, "worktree_health_scan_cursor", []) or [])
            if not cur_cursor:
                units = list_audit_units(base_dir)
                cur_cursor = [str(unit) for unit in units]
                # Drop cache entries for paths that vanished.
                cache_prune_worktree_health_rows(base_dir, set(cur_cursor))
            cached = cache_load_worktree_health_rows(base_dir)
            remaining = list(cur_cursor)
            deadline = time.monotonic() + SCAN_BUDGET_S
            now_scan = int(time.time())
            visited = 0
            while remaining:
                unit_str = remaining[0]
                unit_path = Path(unit_str)
                try:
                    sig = audit_unit_signature(base_dir, unit_path)
                except OSError:
                    remaining.pop(0)
                    continue
                cached_entry = cached.get(unit_str)
                if cached_entry is not None and cached_entry[0] == sig:
                    remaining.pop(0)
                    visited += 1
                    if time.monotonic() >= deadline:
                        break
                    continue
                try:
                    issues = audit_unit(base_dir, unit_path)
                except (OSError, ValueError):
                    issues = []
                payload = [_issue_to_dict(issue) for issue in issues]
                cache_upsert_worktree_health_row(
                    base_dir, unit_str, sig, now_scan, payload
                )
                cached[unit_str] = (sig, now_scan, payload)
                remaining.pop(0)
                visited += 1
                if time.monotonic() >= deadline:
                    break
            aggregate: list[dict[str, object]] = []
            for _path, (_sig, _ts, entries) in cached.items():
                aggregate.extend(entries)
            cache_save_worktree_health(base_dir, now_scan, aggregate)
            app.call_from_thread(
                on_worktree_health_refresh_done,
                app,
                aggregate,
                now_scan,
                remaining,
                visited,
            )
        except (OSError, ValueError):
            app.call_from_thread(_clear_refresh_running, app)

    threading.Thread(target=worker, daemon=True).start()


def _clear_refresh_running(app: Any) -> None:
    app.worktree_health_refresh_running = False


def on_worktree_health_refresh_done(
    app: Any,
    issues: list[dict[str, object]],
    scan_at: int,
    remaining_cursor: list[str] | None = None,
    visited: int = 0,
) -> None:
    app.worktree_health_refresh_running = False
    app.worktree_health_scan_cursor = list(remaining_cursor or [])
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


def action_fix_worktrees(app: Any) -> None:
    """Entry from the action picker. Shows a confirm modal with the
    list of issues, then runs the fix and shows a result modal."""
    issues = audit_workspace(app.base_dir)
    if not issues:
        app._log("worktree health: clean", "info")
        app.worktree_health_issues = []
        _paint_banner(app)
        _show_clean_result(app)
        return

    title = f"Confirm worktree fix: {len(issues)} issue(s)"
    details = _format_issue_list(issues)
    app.push_screen(
        app._confirm_screen_cls(title, details),
        lambda ok: _on_confirm_fix(app, ok, issues),
    )


def _on_confirm_fix(app: Any, ok: bool | None, issues: list) -> None:
    if not ok:
        app._log("worktree fix cancelled", "warn")
        return
    applied = 0
    failed = 0
    per_issue: list[tuple[str, bool, str]] = []
    for issue in issues:
        ok_fix, detail = repair_issue(issue)
        per_issue.append((f"{issue.kind} {issue.path}", ok_fix, detail))
        if ok_fix:
            applied += 1
        else:
            failed += 1
            app._log(f"fix-worktrees {issue.kind} for {issue.path}: {detail}", "error")
    if failed:
        app._log(
            f"worktree fix applied {applied}, failed {failed}; re-running audit",
            "warn",
        )
    else:
        app._log(f"worktree fix applied {applied}", "info")

    refreshed = [_issue_to_dict(issue) for issue in audit_workspace(app.base_dir)]
    cache_save_worktree_health(app.base_dir, int(time.time()), refreshed)
    app.worktree_health_issues = refreshed
    app.worktree_health_last_scan_ts = int(time.time())
    app.worktree_health_dismissed = False
    _paint_banner(app)
    _show_fix_result(
        app,
        applied=applied,
        failed=failed,
        per_issue=per_issue,
        remaining=len(refreshed),
    )


def _format_issue_list(issues: list) -> str:
    lines: list[str] = [
        f"[bold]About to repair {len(issues)} worktree health issue(s).[/]",
        "",
    ]
    for issue in issues:
        kind = getattr(issue, "kind", "unknown")
        path = str(getattr(issue, "path", ""))
        detail = str(getattr(issue, "detail", "") or "").strip()
        fix_summary = str(getattr(issue, "fix_summary", "") or "").strip()
        lines.append(f"[yellow]\\[{kind}][/] {path}")
        if detail:
            lines.append(f"    [dim]issue:[/] {detail}")
        if fix_summary:
            lines.append(f"    [dim]fix:[/]   {fix_summary}")
    lines.append("")
    lines.append("[dim]Some repairs may take a moment.[/]")
    return "\n".join(lines)


def _show_fix_result(
    app: Any,
    *,
    applied: int,
    failed: int,
    per_issue: list[tuple[str, bool, str]],
    remaining: int,
) -> None:
    level = "info"
    if failed and not applied:
        level = "error"
    elif failed:
        level = "warn"
    title = f"Worktree fix: {applied} applied, {failed} failed"
    parts: list[str] = [
        f"applied: {applied}",
        f"failed:  {failed}",
        f"remaining issues after fix: {remaining}",
    ]
    summary = " · ".join(parts)
    detail_lines: list[str] = []
    for label, ok, detail in per_issue:
        marker = "[green]ok[/]" if ok else "[red]fail[/]"
        line = f"{marker} {label}"
        if detail:
            line += f" — {detail}"
        detail_lines.append(line)
    details = "\n".join(detail_lines)
    _push_result_screen(app, title, summary, details, level)
    notifier = getattr(app, "notify", None)
    if callable(notifier):
        severity = "information" if level == "info" else "warning" if level == "warn" else "error"
        notifier(title, severity=severity)


def _show_clean_result(app: Any) -> None:
    title = "Worktree fix: nothing to do"
    summary = "audit found no issues to repair"
    _push_result_screen(app, title, summary, "", "info")
    notifier = getattr(app, "notify", None)
    if callable(notifier):
        notifier("worktree health: clean", severity="information")


def _push_result_screen(
    app: Any, title: str, summary: str, details: str, level: str
) -> None:
    screen_cls = getattr(app, "_result_screen_cls", None)
    if screen_cls is None:
        return
    try:
        app.push_screen(screen_cls(title, summary, details, level=level))
    except WIDGET_API_ERRORS:
        return


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
        f"open Actions (ctrl+a) → Notifications  ·  ctrl+x to dismiss"
    )
    banner.add_class("visible")


def _announce(app: Any, issues: list[dict[str, object]]) -> None:
    kinds: dict[str, int] = {}
    for issue in issues:
        key = str(issue.get("kind", "unknown"))
        kinds[key] = kinds.get(key, 0) + 1
    breakdown = ", ".join(f"{kind}:{count}" for kind, count in sorted(kinds.items()))
    lines = [
        f"worktree health: {len(issues)} issue(s) [{breakdown}] — "
        f"open Actions (ctrl+a) → Notifications → 'Fix worktree health'"
    ]
    for issue in issues:
        kind = str(issue.get("kind", "unknown"))
        path = str(issue.get("path", "")) or "(no path)"
        detail = str(issue.get("detail", "")).strip()
        suffix = f": {detail}" if detail else ""
        lines.append(f"  - [{kind}] {path}{suffix}")
    app._log("\n".join(lines), "warn")


__all__ = [
    "load_initial_health",
    "maybe_refresh_worktree_health",
    "on_worktree_health_refresh_done",
    "dismiss_worktree_health",
    "action_fix_worktrees",
    "BANNER_ID",
]
