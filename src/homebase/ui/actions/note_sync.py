from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from ...core.models import ProjectRow
from ..query.notes_paths import render_notes_template


def note_sync_config(app: Any, operation: str) -> tuple[bool, str]:
    raw_notes_cfg = getattr(app, "notes_config", {})
    notes_cfg = raw_notes_cfg if isinstance(raw_notes_cfg, dict) else {}
    raw_cfg = notes_cfg.get(operation, {}) if isinstance(notes_cfg, dict) else {}
    cfg = raw_cfg if isinstance(raw_cfg, dict) else {}
    rename_raw = notes_cfg.get("rename", {}) if isinstance(notes_cfg, dict) else {}
    rename_cfg = rename_raw if isinstance(rename_raw, dict) else {}
    if operation != "rename" and not cfg and rename_cfg:
        enabled = bool(rename_cfg.get("enabled", True))
        command = str(rename_cfg.get("command", "") or "").strip()
        return enabled, command
    enabled = bool(cfg.get("enabled", True))
    command = str(cfg.get("command", "") or "").strip()
    return enabled, command


def build_note_sync_command(
    app: Any,
    *,
    source_row: ProjectRow,
    target_row: ProjectRow,
    old_note_path: Path,
    new_note_path: Path,
    command_template: str,
) -> str:
    context = app._notes_template_context(target_row)
    new_note_name = str(new_note_path.stem)
    if bool(target_row.archived):
        new_note_name = str(context.get("NAME_WITH_ARCHIVE_PREFIX", new_note_name))
    old_note_name = str(old_note_path.stem)
    source_context = app._notes_template_context(source_row)
    if bool(source_row.archived):
        old_note_name = str(source_context.get("NAME_WITH_ARCHIVE_PREFIX", old_note_name))
    if bool(source_row.archived) and not bool(target_row.archived):
        new_note_name = f"../{new_note_name}{new_note_path.suffix}"
    old_note_file = f"{old_note_name}{old_note_path.suffix}"
    new_note_file = f"{new_note_name}{new_note_path.suffix}"
    context.update(
        {
            "OLD_NOTE_PATH": str(old_note_path),
            "OLD_NOTE_PATH_Q": shlex.quote(str(old_note_path)),
            "NEW_NOTE_PATH": str(new_note_path),
            "NEW_NOTE_PATH_Q": shlex.quote(str(new_note_path)),
            "OLD_NOTE_NAME": old_note_name,
            "NEW_NOTE_NAME": new_note_name,
            "OLD_NOTE_FILE": old_note_file,
            "NEW_NOTE_FILE": new_note_file,
            "OLD_PROJECT_NAME": str(source_row.name),
            "NEW_PROJECT_NAME": str(target_row.name),
        }
    )
    for key, value in list(context.items()):
        context[key.lower()] = value
    return render_notes_template(command_template, context).strip()
