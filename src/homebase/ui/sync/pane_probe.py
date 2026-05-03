from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from textual.css.query import NoMatches

from ...core.models import PaneRef
from ...core.utils import WIDGET_API_ERRORS


def project_for_path(cwd: Path, project_roots: set[Path]) -> Path | None:
    cur = cwd
    while True:
        if cur in project_roots:
            return cur
        if cur == cur.parent:
            return None
        cur = cur.parent


def start_probe_open_panes(app: Any) -> None:
    if app.fast_exit_requested or app.pane_probe_running:
        return
    if not os.getenv("TMUX"):
        if app.open_panes_by_project:
            app.open_panes_by_project = {}
            app.open_pane_count_by_project = {}
            app.open_pane_overflow_projects = set()
            app._apply_dynamic_properties_all_rows()
            app._refresh_table()
            app._refresh_side()
        app.pane_probe_next_due_at = time.time() + app._pane_probe_desired_interval_s()
        return
    app.pane_probe_running = True

    def worker() -> None:
        mapping: dict[Path, list[PaneRef]] = {}
        try:
            rows_all = app.active_rows + app.archived_rows
            project_roots = {row.path.resolve() for row in rows_all}
            if not project_roots:
                app.call_from_thread(app._on_probe_open_panes_done, mapping)
                return

            proc = subprocess.run(
                [
                    "tmux",
                    "list-panes",
                    "-a",
                    "-F",
                    "#{pane_id}\t#{session_name}:#{window_index}.#{pane_index}\t#{window_name}\t#{pane_current_command}\t#{pane_current_path}\t#{?pane_active,1,0}",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            if proc.returncode != 0:
                app.call_from_thread(app._on_probe_open_panes_done, mapping)
                return

            for line in proc.stdout.splitlines():
                parts = line.split("\t", 5)
                if len(parts) != 6:
                    continue
                pane_id, target, window_name, cmd, cwd_raw, active_raw = parts
                cwd_raw = cwd_raw.strip()
                if not cwd_raw:
                    continue
                try:
                    cwd = Path(cwd_raw).resolve()
                except (OSError, ValueError):
                    continue
                project = project_for_path(cwd, project_roots)
                if project is None:
                    continue
                pref = PaneRef(
                    pane_id=pane_id.strip(),
                    target=target.strip(),
                    window_name=window_name.strip(),
                    command=cmd.strip(),
                    cwd=cwd,
                    active=(active_raw.strip() == "1"),
                )
                mapping.setdefault(project, []).append(pref)
        except (subprocess.SubprocessError, OSError, ValueError):
            pass
        app.call_from_thread(app._on_probe_open_panes_done, mapping)

    threading.Thread(target=worker, daemon=True).start()


def on_probe_open_panes_done(app: Any, mapping: dict[Path, list[PaneRef]]) -> None:
    if app.fast_exit_requested:
        return
    app.pane_probe_running = False
    app.open_panes_by_project = mapping
    app.open_pane_count_by_project = {path: len(panes) for path, panes in mapping.items()}
    app.open_pane_overflow_projects = {
        path for path, panes in mapping.items() if len(panes) > 9
    }

    sig_parts = [
        f"{str(path)}:{len(mapping[path])}" for path in sorted(mapping.keys(), key=str)
    ]
    sig = "|".join(sig_parts)
    if sig != app.pane_state_sig:
        app.pane_state_sig = sig
        app._apply_dynamic_properties_all_rows()
        try:
            app._refresh_table()
            app._refresh_side()
        except (*WIDGET_API_ERRORS, NoMatches):
            return

    app.pane_probe_last_done_ts = time.time()
    app.pane_probe_next_due_at = time.time() + app._pane_probe_desired_interval_s()


def pane_probe_desired_interval_s(app: Any) -> float:
    if not os.getenv("TMUX"):
        return 30.0
    now = time.time()
    if now < app.pane_probe_fast_until_ts:
        return app.pane_probe_interval_fast_s
    if app.view_mode == "active":
        visible = {
            str(c.get("id", "")).strip()
            for c in app._table_visible_columns_for_view(app.view_mode)
        }
        if "properties" in visible:
            return app.pane_probe_interval_fast_s
    query = app.query.lower().strip()
    if "act" in query:
        return app.pane_probe_interval_fast_s
    return app.pane_probe_interval_slow_s


def maybe_probe_open_panes(app: Any) -> None:
    if app.fast_exit_requested:
        return
    if app.pane_probe_running:
        return
    now = time.time()
    if (now - float(getattr(app, "pane_probe_last_done_ts", 0.0))) < float(
        getattr(app, "pane_probe_min_interval_s", 0.5)
    ):
        return
    if now < app.pane_probe_next_due_at:
        return
    app._start_probe_open_panes()
