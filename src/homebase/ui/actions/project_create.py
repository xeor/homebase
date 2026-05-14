from __future__ import annotations

import contextlib
import io
import sqlite3
import subprocess
from argparse import Namespace
from pathlib import Path
from typing import Any

from ...cache.api import cache_upsert_project_fast
from ...workspace.new.base import NewContext
from ...workspace.new.cmd import format_summary, plan_and_apply_one
from ...workspace.new.config_loader import NewConfigError, load_new_sources
from ...workspace.new.registry import builtin_keys
from ...workspace.projects import project_row


def action_new_project(app: Any, *, base_dir: Path, new_project_screen: Any) -> None:
    app.push_screen(
        new_project_screen(base_dir, allow_stay_in_b=not app.start_new_mode),
        app._on_new_project_submit,
    )


def _payload_to_namespace(payload: dict[str, object]) -> Namespace:
    """Translate the modal's payload into the same Namespace shape the
    CLI dispatcher produces, so `plan_and_apply_one` can consume it."""
    raw_input = str(payload.get("input", "") or "").strip()
    name = str(payload.get("name", "") or "").strip()
    source = str(payload.get("source", "auto") or "auto").strip()
    template = str(payload.get("template", "") or "")

    inputs: list[str] = []
    if raw_input:
        inputs.append(raw_input)
    if name:
        inputs.append(name)

    mode: str | None = None
    child_key: str | None = None
    if source != "auto":
        if source in set(builtin_keys()):
            mode = source
        else:
            child_key = source

    tags = payload.get("tags") or []
    if isinstance(tags, list):
        tag_list = [str(t) for t in tags if str(t).strip()]
    else:
        tag_list = []

    def _flag(value: object) -> bool | None:
        if value is None:
            return None
        return bool(value)

    return Namespace(
        inputs=inputs,
        mode=mode,
        child_key=child_key,
        tag=tag_list,
        template=template,
        tmp=_flag(payload.get("tmp")),
        timestamp=_flag(payload.get("timestamp")),
        open=_flag(payload.get("cd")),
        cd=_flag(payload.get("cd")),
        confirm=_flag(payload.get("confirm")),
        ts_name=_flag(payload.get("ts_name")),
        alpha_name=_flag(payload.get("alpha_name")),
        ask_name=None,
        ask_source=None,
        post=[],
        yes=True,        # the modal already confirmed
        dry_run=None,
        archive=_flag(payload.get("archive")),
        multi=None,
    )


def on_new_project_submit(
    app: Any,
    payload: dict[str, object] | None,
    *,
    base_dir: Path,
) -> None:
    if payload is None:
        app._log("new project cancelled", "warn")
        if app.start_new_mode:
            app.exit(("quit", None, []))
        app._refresh_side()
        return

    try:
        sources_cfg = load_new_sources(base_dir)
    except NewConfigError as exc:
        app._show_runtime_error("new project config", exc)
        if app.start_new_mode:
            app.exit(("quit", None, []))
        app._refresh_side()
        return

    ns = _payload_to_namespace(payload)
    ctx = NewContext(base_dir=base_dir, cwd=Path.cwd().resolve())
    raw_input = ns.inputs[0] if ns.inputs else None
    explicit_name = ns.inputs[1] if len(ns.inputs) > 1 else None

    after_create = str(payload.get("after_create", "open") or "open").strip() or "open"

    # ``plan_and_apply_one`` writes the actual failure reason to
    # stderr via ``print(..., file=sys.stderr)``. Inside the TUI that
    # goes to the void — we capture it so we can surface it to the
    # user after the modal closes (see the ``last_new_*`` attributes
    # below + ``run_textual_ui`` in ui/app.py which prints them).
    captured_err = io.StringIO()
    app._busy_start("creating project")
    plan_obj = None
    try:
        with contextlib.redirect_stderr(captured_err):
            rc, result, plan_obj = plan_and_apply_one(
                ns, raw_input, explicit_name, sources_cfg, ctx,
            )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        app._show_runtime_error("new project", exc)
        rc, result = 1, None
    finally:
        if app._busy_depth > 0:
            app._busy_stop()

    if rc != 0 or result is None:
        err_text = captured_err.getvalue().strip()
        app.last_new_error = err_text or "new project: unknown failure"
        app._log(f"new project failed: {err_text or 'see terminal'}", "error")
        if app.start_new_mode:
            app.exit(("quit", None, []))
        app._refresh_side()
        return

    created = result.target
    if plan_obj is not None:
        app.last_new_summary = format_summary(plan_obj)
    else:
        app.last_new_summary = f"created: {created}"

    if after_create == "open" or app.start_new_mode:
        cache_upsert_project_fast(base_dir, created)
        tags = payload.get("tags") or []
        if isinstance(tags, list) and tags:
            app._request_tag_sync("new project")
        app._log(f"new project created: {created.name}", "info")
        app.exit(("open", created, []))
        return

    try:
        new_row = project_row(created, archived=False)
        app._upsert_row_local(new_row)
        app._touch_rows_cache([new_row])
    except (OSError, ValueError, TypeError, subprocess.SubprocessError, sqlite3.Error):
        app._refresh_data()

    app.selected_path = created
    app.multi_selected.clear()
    app._refresh_table()
    tags = payload.get("tags") or []
    if isinstance(tags, list) and tags:
        app._request_tag_sync("new project")
    app._log(f"new project created: {created.name}", "info")
    app._refresh_side()
