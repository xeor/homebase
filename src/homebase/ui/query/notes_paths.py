from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Any, Callable

from ...core.models import ProjectRow


def selected_readme_path(app: Any) -> Path | None:
    selected = app._selected_row()
    if selected is None:
        return None
    if selected.packed:
        return None
    try:
        if not selected.path.is_dir():
            return None
    except OSError:
        return None
    path = selected.path / "README.md"
    try:
        if path.is_file():
            return path
    except OSError:
        return None
    return None


def notes_template_context(
    app: Any,
    row: ProjectRow,
    *,
    base_dir: Path,
    fmt_ymd: Callable[[int], str],
) -> dict[str, str]:
    rel_path = row.path
    try:
        rel_path = row.path.relative_to(base_dir)
    except ValueError:
        pass
    restore_to = str(row.restore_target) if row.restore_target is not None else ""
    archive_prefix = "_archive/" if row.archived else ""
    archive_name = row.name
    if row.archived:
        if row.archived_ts > 0:
            archive_name = f"{fmt_ymd(row.archived_ts)}_{row.name}"
    archive_prefixed_name = f"{archive_prefix}{archive_name}"
    out = {
        "NAME": row.name,
        "PROJECT_NAME": row.name,
        "NAME_WITH_ARCHIVE_PREFIX": archive_prefixed_name,
        "ARCHIVE_PREFIX": archive_prefix,
        "PROJECT_PATH": str(row.path),
        "FULL_PATH": str(row.path),
        "REL_PATH": str(rel_path),
        "BASE_DIR": str(base_dir),
        "VIEW_MODE": app.view_mode,
        "BRANCH": row.branch,
        "DESCRIPTION": row.description,
        "TAGS": ",".join(row.tags),
        "PROPERTIES": ",".join(row.properties),
        "ARCHIVED": "1" if row.archived else "0",
        "PACKED": "1" if row.packed else "0",
        "RESTORE_TARGET": restore_to,
        "CREATED": row.created,
        "LAST_MODIFIED": row.last,
        "LAST_OPENED": fmt_ymd(row.opened_ts) if row.opened_ts > 0 else "",
    }
    for key, value in list(out.items()):
        out[key.lower()] = value
    out["NAME_WITH_ARCHIVE_PREFIX_Q"] = shlex.quote(archive_prefixed_name)
    out["name_with_archive_prefix_q"] = out["NAME_WITH_ARCHIVE_PREFIX_Q"]
    return out


def render_notes_template(template_text: str, context: dict[str, str]) -> str:
    pattern = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
    return pattern.sub(lambda m: str(context.get(m.group(1), "")), template_text)


def resolve_notes_path_for_row(app: Any, row: ProjectRow, *, base_dir: Path) -> Path:
    template = str(app.notes_config.get("path_template", "")).strip()
    if not template:
        raise ValueError("notes.path_template is empty")
    context = app._notes_template_context(row)
    path_context = dict(context)
    for key, value in context.items():
        if not key.endswith("_Q"):
            continue
        raw_key = key[:-2]
        raw_value = context.get(raw_key)
        if raw_value is not None:
            path_context[key] = raw_value
        else:
            path_context[key] = value
    rendered = render_notes_template(template, path_context).strip()
    if not rendered:
        raise ValueError("notes.path_template rendered to empty path")
    expanded = os.path.expandvars(rendered)
    candidate = Path(expanded).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate.resolve(strict=False)


def selected_notes_path(app: Any) -> Path | None:
    selected = app._selected_row()
    if selected is None:
        return None
    try:
        path = app._resolve_notes_path_for_row(selected)
    except (OSError, ValueError, RuntimeError):
        return None
    try:
        if path.is_file():
            return path
    except OSError:
        return None
    return None
