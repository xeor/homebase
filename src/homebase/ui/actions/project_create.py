from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import yaml

from ...cache.api import cache_upsert_project_fast
from ...config.prefs import load_new_project_defaults, save_new_project_defaults
from ...workspace.projects import create_project, project_row, resolve_new_project_name


def action_new_project(app: Any, *, base_dir: Path, new_project_screen: Any) -> None:
    app.push_screen(
        new_project_screen(base_dir, allow_stay_in_b=not app.start_new_mode),
        app._on_new_project_submit,
    )


def on_new_project_submit(
    app: Any,
    payload: dict[str, str | None] | None,
    *,
    base_dir: Path,
) -> None:
    if payload is None:
        app._log("new project cancelled", "warn")
        if app.start_new_mode:
            app.exit(("quit", None, []))
        app._refresh_side()
        return

    folder_name = str(payload.get("folder_name", "")).strip()
    template_name = payload.get("template")
    template_value = str(template_name).strip() if template_name is not None else None
    add_date_prefix = str(payload.get("add_date_prefix", "0")).strip() == "1"
    add_tmp_suffix = str(payload.get("add_tmp_suffix", "0")).strip() == "1"
    post_commands_text = str(payload.get("post_commands", "")).strip()
    post_commands = [line.strip() for line in post_commands_text.splitlines() if line.strip()]
    tags_text = str(payload.get("tags", "")).strip()
    selected_tags = [line.strip() for line in tags_text.splitlines() if line.strip()]
    after_create = str(payload.get("after_create", "open")).strip() or "open"

    try:
        persisted_after_create = after_create
        if app.start_new_mode:
            prior = load_new_project_defaults(base_dir)
            persisted_after_create = str(prior.get("after_create", "open")).strip() or "open"
        save_new_project_defaults(
            base_dir,
            {
                "name_options": [
                    key
                    for key, enabled in (
                        ("date_prefix", add_date_prefix),
                        ("tmp_suffix", add_tmp_suffix),
                    )
                    if enabled
                ],
                "template": template_value,
                "post_commands": post_commands,
                "tags": selected_tags,
                "after_create": persisted_after_create,
            },
        )
    except (OSError, yaml.YAMLError, TypeError, ValueError) as exc:
        app._show_runtime_error("save new-project defaults", exc)

    try:
        resolved_name = resolve_new_project_name(folder_name, add_date_prefix, add_tmp_suffix)
    except ValueError as exc:
        app._log(f"new project failed: {exc}", "error")
        if app.start_new_mode:
            app.exit(("quit", None, []))
        app._refresh_side()
        return
    target = base_dir / resolved_name

    if target.exists():
        app._log(f"opened existing: {target.name}", "info")
        app.exit(("open", target, []))
        return

    app._busy_start("creating project")
    try:
        created = create_project(
            base_dir,
            folder_name,
            add_date_prefix,
            add_tmp_suffix,
            template_value,
            selected_tags,
        )
    except ValueError as exc:
        app._log(f"new project failed: {exc}", "error")
        if app.start_new_mode:
            app.exit(("quit", None, []))
        app._refresh_side()
        app._busy_stop()
        return
    finally:
        if app._busy_depth > 0:
            app._busy_stop()

    if after_create == "open" or app.start_new_mode:
        cache_upsert_project_fast(base_dir, created)
        if selected_tags:
            app._request_tag_sync("new project")
        app._log(f"new project created: {created.name}", "info")
        app.exit(("open", created, post_commands))
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
    if selected_tags:
        app._request_tag_sync("new project")
    app._log(f"new project created: {created.name}", "info")
    app._refresh_side()
