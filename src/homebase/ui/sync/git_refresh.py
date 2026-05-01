from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from ...core.models import ProjectRow
from ...workspace.projects import git_info
from ...workspace.rows import fmt_ymd


def maybe_refresh_visible_git(app: Any) -> None:
    if app.fast_exit_requested:
        return
    if app._critical_job_active():
        return
    if app.git_refresh_running:
        return
    if app.cache_worker_running:
        return
    if time.time() - app.git_refresh_last_ts < 0.5:
        return

    rows = app._current_rows()
    if not rows:
        return

    candidates: list[Path] = []
    selected = app._selected_row()
    if (
        selected is not None
        and selected.branch not in {"-", "?"}
        and selected.dirty in {"~", "?"}
    ):
        candidates.append(selected.path)

    for row in rows[:36]:
        if row.branch in {"-", "?"}:
            continue
        if row.dirty not in {"~", "?"}:
            continue
        candidates.append(row.path)
        if len(candidates) >= 8:
            break

    if not candidates:
        return
    uniq: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        uniq.append(path)
    app._start_git_refresh(uniq, "visible")


def start_git_refresh(app: Any, paths: list[Path], reason: str) -> None:
    if app.git_refresh_running or not paths:
        return
    specs: list[Path] = []
    for path in paths:
        hit = app._find_row(path)
        if hit is None:
            continue
        rows, idx = hit
        row = rows[idx]
        if row.branch in {"-", "?"}:
            continue
        specs.append(row.path)
    if not specs:
        return

    app.git_refresh_running = True
    app.git_refresh_paths = set(specs)
    app.git_refresh_reason = reason
    app.git_refresh_last_ts = time.time()
    app._refresh_table()
    app._refresh_side()

    def worker() -> None:
        updated: list[tuple[Path, str, str, int]] = []
        for path in specs:
            try:
                if not path.exists():
                    continue
                branch, dirty, git_ts = git_info(path, include_dirty=True)
                updated.append((path, branch, dirty, git_ts))
            except (OSError, ValueError, subprocess.SubprocessError):
                continue
        app.call_from_thread(app._on_git_refresh_done, updated)

    threading.Thread(target=worker, daemon=True).start()


def on_git_refresh_done(app: Any, updated: list[tuple[Path, str, str, int]]) -> None:
    app.git_refresh_running = False
    app.git_refresh_paths = set()
    app.git_refresh_reason = ""
    app.git_refresh_last_ts = time.time()
    now_ts = int(time.time())
    touched: list[ProjectRow] = []
    for path, branch, dirty, git_ts in updated:
        hit = app._find_row(path)
        if hit is None:
            continue
        rows, idx = hit
        row = rows[idx]
        row.branch = branch
        row.dirty = dirty
        row.git_ts = git_ts
        if git_ts > 0:
            row.last_ts = git_ts
            row.last = fmt_ymd(git_ts)
            row.src = "git"
        else:
            row.src = "fs"
        row.last_cached_ts = now_ts
        touched.append(row)
    if touched:
        app._touch_rows_cache(touched)
    app._refresh_table()
    app._refresh_side()
