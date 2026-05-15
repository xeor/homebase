from __future__ import annotations

import contextlib
import io
import sqlite3
import subprocess
from argparse import Namespace
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from ...cache.api import cache_upsert_project_fast
from ...hooks import runtime as hooks_runtime
from ...hooks.snapshot import snapshot_target
from ...metadata.api import load_base_data
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
    pre_outcome = hooks_runtime.dispatch_pre(
        app,
        event="new_project",
        targets=[],
        change={
            "source": str(ns.mode or ns.child_key or "auto"),
            "template": (str(ns.template).strip() if str(ns.template).strip() else None),
            "initial_tags": [str(tag) for tag in (payload.get("tags") or []) if str(tag).strip()],
            "post_commands": [str(cmd) for cmd in (payload.get("post_commands") or []) if str(cmd).strip()],
            "after_create": after_create,
            "inputs": {
                "raw_input": raw_input,
                "explicit_name": explicit_name,
                "mode": ns.mode,
                "child_key": ns.child_key,
                "tmp": ns.tmp,
                "timestamp": ns.timestamp,
                "ts_name": ns.ts_name,
                "alpha_name": ns.alpha_name,
                "ask_name": ns.ask_name,
                "ask_source": ns.ask_source,
                "archive": ns.archive,
                "multi": ns.multi,
            },
        },
        view=app.view_mode,
    )
    if pre_outcome.cancelled:
        app._log(f"new project cancelled by hook: {pre_outcome.reason}", "warn")
        if app.start_new_mode:
            app.exit(("quit", None, []))
        app._refresh_side()
        return
    _apply_pre_new_project_mutations(
        payload=payload,
        ns=ns,
        change=pre_outcome.change,
    )
    raw_input = ns.inputs[0] if ns.inputs else None
    explicit_name = ns.inputs[1] if len(ns.inputs) > 1 else None
    after_create = str(pre_outcome.change.get("after_create", after_create) or after_create)

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
        _dispatch_new_project_hook(
            app,
            base_dir=base_dir,
            created=created,
            payload=payload,
            after_create=after_create,
            ns=ns,
            raw_input=raw_input,
            explicit_name=explicit_name,
            plan_obj=plan_obj,
        )
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
    _dispatch_new_project_hook(
        app,
        base_dir=base_dir,
        created=created,
        payload=payload,
        after_create=after_create,
        ns=ns,
        raw_input=raw_input,
        explicit_name=explicit_name,
        plan_obj=plan_obj,
    )
    app._log(f"new project created: {created.name}", "info")
    app._refresh_side()


def _to_plain(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _to_plain(asdict(value))
    if isinstance(value, Namespace):
        return {key: _to_plain(val) for key, val in vars(value).items()}
    if isinstance(value, dict):
        return {str(key): _to_plain(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, tuple):
        return [_to_plain(item) for item in value]
    return value


def _apply_pre_new_project_mutations(
    *,
    payload: dict[str, object],
    ns: Namespace,
    change: dict[str, object],
) -> None:
    initial_tags = change.get("initial_tags")
    if isinstance(initial_tags, list):
        payload["tags"] = [str(tag) for tag in initial_tags if str(tag).strip()]
        ns.tag = [str(tag) for tag in initial_tags if str(tag).strip()]
    post_commands = change.get("post_commands")
    if isinstance(post_commands, list):
        payload["post_commands"] = [str(cmd) for cmd in post_commands if str(cmd).strip()]
    template = change.get("template")
    if template is not None:
        text = str(template).strip()
        payload["template"] = text
        ns.template = text
    source = change.get("source")
    if source is not None:
        source_text = str(source).strip()
        if source_text in set(builtin_keys()):
            ns.mode = source_text
            ns.child_key = None
        elif source_text:
            ns.mode = None
            ns.child_key = source_text


def _dispatch_new_project_hook(
    app: Any,
    *,
    base_dir: Path,
    created: Path,
    payload: dict[str, object],
    after_create: str,
    ns: Namespace,
    raw_input: str | None,
    explicit_name: str | None,
    plan_obj: object,
) -> None:
    try:
        row = project_row(created, archived=False)
        target = snapshot_target(row, load_base_data(created))
    except (OSError, ValueError, TypeError, subprocess.SubprocessError, sqlite3.Error):
        return
    hooks_runtime.dispatch_post(
        app,
        event="new_project",
        targets=[target],
        change={
            "created_path": created,
            "source": str(ns.mode or ns.child_key or "auto"),
            "template": (str(ns.template).strip() if str(ns.template).strip() else None),
            "initial_tags": [str(tag) for tag in (payload.get("tags") or []) if str(tag).strip()],
            "post_commands": [str(cmd) for cmd in (payload.get("post_commands") or []) if str(cmd).strip()],
            "after_create": after_create,
            "inputs": {
                "raw_input": raw_input,
                "explicit_name": explicit_name,
                "mode": ns.mode,
                "child_key": ns.child_key,
                "tmp": ns.tmp,
                "timestamp": ns.timestamp,
                "ts_name": ns.ts_name,
                "alpha_name": ns.alpha_name,
                "ask_name": ns.ask_name,
                "ask_source": ns.ask_source,
                "archive": ns.archive,
                "multi": ns.multi,
            },
            "plan": _to_plain(plan_obj) if plan_obj is not None else {},
        },
        view=app.view_mode,
    )
