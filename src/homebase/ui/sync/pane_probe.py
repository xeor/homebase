from __future__ import annotations

import functools
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from ...core.models import PaneRef
from ...tmux.external import (
    external_tmux_command_prefix_and_session,
    is_inside_current_tmux_pane,
)


@functools.lru_cache(maxsize=8192)
def _resolved_path_str(path_str: str) -> str | None:
    try:
        return str(Path(path_str).resolve())
    except (OSError, RuntimeError, ValueError):
        return None


def _resolve_cached(path: Path) -> Path | None:
    resolved = _resolved_path_str(str(path))
    return Path(resolved) if resolved is not None else None


def project_for_path(cwd: Path, project_roots: set[Path]) -> Path | None:
    cur = cwd
    while True:
        if cur in project_roots:
            return cur
        if cur == cur.parent:
            return None
        cur = cur.parent


def _rows_to_probe(app: Any, scan_limit: int) -> list[Any]:
    rows: list[Any] = []
    seen: set[Path] = set()
    for row in [*app._current_rows(), *app.active_rows, *app.archived_rows]:
        path = row.path
        if path in seen:
            continue
        rows.append(row)
        seen.add(path)
        if len(rows) >= scan_limit:
            break
    return rows


def start_probe_open_panes(app: Any) -> None:
    if app.fast_exit_requested or app.pane_probe_running:
        return
    tmux_prefix = ["tmux"]
    tmux_session_target = ""
    if not is_inside_current_tmux_pane():
        base_dir = getattr(app, "base_dir", None)
        resolved = (
            None
            if base_dir is None
            else external_tmux_command_prefix_and_session(base_dir, quiet=True)
        )
        if resolved is not None:
            tmux_prefix, tmux_session_target = resolved
        else:
            if app.open_panes_by_project:
                changed_paths = list(app.open_panes_by_project.keys())
                app.open_panes_by_project = {}
                app.open_pane_count_by_project = {}
                app.open_pane_overflow_projects = set()
                app._queue_dynamic_property_refresh(changed_paths)
            app.pane_probe_next_due_at = time.time() + app._pane_probe_desired_interval_s()
            return
    app.pane_probe_running = True

    def worker() -> None:
        mapping: dict[Path, list[PaneRef]] = {}
        try:
            scan_limit = app._pane_probe_project_scan_limit()
            rows_all = _rows_to_probe(app, scan_limit)
            project_root_to_row_path: dict[Path, Path] = {}
            for row in rows_all:
                resolved = _resolve_cached(row.path)
                if resolved is not None:
                    project_root_to_row_path.setdefault(resolved, row.path)
            if not project_root_to_row_path:
                app.call_from_thread(app._on_probe_open_panes_done, mapping)
                return
            project_roots = set(project_root_to_row_path)

            proc = subprocess.run(
                [
                    *tmux_prefix,
                    "list-panes",
                    *(
                        ["-s", "-t", tmux_session_target]
                        if tmux_session_target
                        else ["-a"]
                    ),
                    "-F",
                    "#{pane_id}\t#{session_name}:#{window_index}.#{pane_index}\t#{window_name}\t#{pane_current_command}\t#{pane_current_path}\t#{?pane_active,1,0}",
                ],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            if proc.returncode != 0:
                detail = (proc.stderr or "").strip() or f"exit {proc.returncode}"
                app.call_from_thread(
                    on_probe_open_panes_failed,
                    app,
                    f"tmux pane probe failed: {detail}",
                )
                return

            for line in proc.stdout.splitlines():
                parts = line.split("\t", 5)
                if len(parts) != 6:
                    continue
                pane_id, target, window_name, cmd, cwd_raw, active_raw = parts
                cwd_raw = cwd_raw.strip()
                if not cwd_raw:
                    continue
                cwd = _resolve_cached(Path(cwd_raw))
                if cwd is None:
                    continue
                project_root = project_for_path(cwd, project_roots)
                if project_root is None:
                    continue
                project = project_root_to_row_path[project_root]
                pref = PaneRef(
                    pane_id=pane_id.strip(),
                    target=target.strip(),
                    window_name=window_name.strip(),
                    command=cmd.strip(),
                    cwd=cwd,
                    active=(active_raw.strip() == "1"),
                )
                mapping.setdefault(project, []).append(pref)
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            app.call_from_thread(
                on_probe_open_panes_failed,
                app,
                f"tmux pane probe failed: {exc}",
            )
            return
        app.call_from_thread(app._on_probe_open_panes_done, mapping)

    threading.Thread(target=worker, daemon=True).start()


def _log_probe_result(app: Any, mapping: dict[Path, list[PaneRef]]) -> None:
    log = getattr(app, "_log", None)
    if not callable(log):
        return
    pane_total = sum(len(panes) for panes in mapping.values())
    log(f"tmux pane probe: projects={len(mapping)} panes={pane_total}", "info")


def _changed_pane_count_paths(
    previous: dict[Path, int],
    current: dict[Path, int],
) -> list[Path]:
    paths = {*previous, *current}
    return sorted(
        (
            path
            for path in paths
            if int(previous.get(path, 0)) != int(current.get(path, 0))
        ),
        key=str,
    )


def _refresh_probe_views(app: Any) -> None:
    for method_name in ("_refresh_table", "_refresh_side"):
        refresh = getattr(app, method_name, None)
        if callable(refresh):
            refresh()


def on_probe_open_panes_failed(app: Any, message: str) -> None:
    if app.fast_exit_requested:
        return
    app.pane_probe_running = False
    log = getattr(app, "_log", None)
    if callable(log):
        log(message, "warn")
    app.pane_probe_next_due_at = time.time() + app._pane_probe_desired_interval_s()


def on_probe_open_panes_done(app: Any, mapping: dict[Path, list[PaneRef]]) -> None:
    if app.fast_exit_requested:
        return
    app.pane_probe_running = False
    prev_counts = dict(app.open_pane_count_by_project)
    app.open_panes_by_project = mapping
    app.open_pane_count_by_project = {path: len(panes) for path, panes in mapping.items()}
    app.open_pane_overflow_projects = {
        path for path, panes in mapping.items() if len(panes) > 9
    }
    _log_probe_result(app, mapping)

    sig_parts = [
        f"{str(path)}:{len(mapping[path])}" for path in sorted(mapping.keys(), key=str)
    ]
    sig = "|".join(sig_parts)
    if sig != app.pane_state_sig:
        app.pane_state_sig = sig
        changed_paths = _changed_pane_count_paths(
            prev_counts,
            app.open_pane_count_by_project,
        )
        app._queue_dynamic_property_refresh(changed_paths)
        _refresh_probe_views(app)

    app.pane_probe_last_done_ts = time.time()
    app.pane_probe_next_due_at = time.time() + app._pane_probe_desired_interval_s()


def pane_probe_desired_interval_s(app: Any) -> float:
    if not is_inside_current_tmux_pane():
        return app._pane_probe_profile_slow_interval_s()
    fast_interval_s = app._pane_probe_profile_fast_interval_s()
    slow_interval_s = app._pane_probe_profile_slow_interval_s()
    now = time.time()
    if now < app.pane_probe_fast_until_ts:
        return fast_interval_s
    if app.view_mode == "active":
        visible = {
            str(c.get("id", "")).strip()
            for c in app._table_visible_columns_for_view(app.view_mode)
        }
        if "properties" in visible:
            return fast_interval_s
    query = app.query.lower().strip()
    if "act" in query:
        return fast_interval_s
    return slow_interval_s


def maybe_probe_open_panes(app: Any) -> None:
    if app.fast_exit_requested:
        return
    if app.pane_probe_running:
        return
    now = time.time()
    if (now - float(getattr(app, "pane_probe_last_done_ts", 0.0))) < float(
        app._pane_probe_profile_min_interval_s()
    ):
        return
    if now < app.pane_probe_next_due_at:
        return
    app._start_probe_open_panes()
