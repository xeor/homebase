from __future__ import annotations

import os
import re
import shlex
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any

from ...core.models import ProjectRow

_VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

PER_ROW_VARS: set[str] = {
    "path",
    "path_q",
    "rel_path",
    "rel_path_q",
    "name",
    "name_q",
    "parent_path",
    "parent_path_q",
    "branch",
    "branch_q",
    "dirty",
    "description",
    "description_q",
    "tags",
    "tags_space",
    "tags_space_q",
    "properties",
    "suffix",
    "wip",
    "archived",
    "packed",
    "created",
    "created_iso",
    "created_ts",
    "last_modified",
    "last_modified_iso",
    "last_modified_ts",
    "last_opened",
    "last_opened_iso",
    "last_opened_ts",
    "archived_at",
    "archived_at_iso",
    "archived_at_ts",
    "size_bytes",
    "size_human",
    "note_path",
    "note_path_q",
}

LIST_VARS: set[str] = {
    "paths",
    "paths_q",
    "rel_paths",
    "rel_paths_q",
    "names",
    "names_q",
}

FILEPICKER_VARS: set[str] = {"selection", "selection_q"}

ALWAYS_VARS: set[str] = {
    "base_dir",
    "base_dir_q",
    "base_name",
    "archive_dir",
    "archive_dir_q",
    "active_count",
    "archive_count",
    "wip_count",
    "count",
    "view",
    "filter",
    "filter_q",
    "now",
    "now_iso",
    "now_ts",
    "today",
    "user",
    "home",
    "home_q",
}


def _quote(value: str) -> str:
    return shlex.quote(str(value))


def _fmt_iso(ts: int) -> str:
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def _fmt_ymd(ts: int) -> str:
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%d")


def _fmt_human_bytes(size_bytes: int) -> str:
    n = max(0, int(size_bytes))
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(n)
    unit = units[0]
    for candidate in units:
        unit = candidate
        if v < 1024.0 or candidate == units[-1]:
            break
        v /= 1024.0
    if unit == "B":
        return f"{int(v)}B"
    return f"{v:.1f}{unit}"


def build_per_row_context(app: Any, row: ProjectRow, base_dir: Path) -> dict[str, str]:
    row_path = Path(str(getattr(row, "path", "")))
    rel = row_path
    try:
        rel = row_path.relative_to(base_dir)
    except ValueError:
        pass
    note_path = ""
    try:
        note = app._resolve_notes_path_for_row(row)
        note_path = str(note)
    except (OSError, ValueError, RuntimeError, AttributeError):
        note_path = ""
    row_name = str(getattr(row, "name", row_path.name))
    row_tags = list(getattr(row, "tags", []))
    row_props = list(getattr(row, "properties", []))
    row_desc = str(getattr(row, "description", ""))
    row_dirty = str(getattr(row, "dirty", ""))
    row_branch = str(getattr(row, "branch", "-"))
    row_suffix = str(getattr(row, "suffix", "") or "")
    row_created = str(getattr(row, "created", ""))
    row_last = str(getattr(row, "last", ""))
    row_created_ts = int(getattr(row, "created_ts", 0) or 0)
    row_last_ts = int(getattr(row, "last_ts", 0) or 0)
    row_opened_ts = int(getattr(row, "opened_ts", 0) or 0)
    row_archived_ts = int(getattr(row, "archived_ts", 0) or 0)
    row_size_bytes = int(getattr(row, "size_bytes", 0) or 0)
    row_wip = bool(getattr(row, "wip", False))
    row_archived = bool(getattr(row, "archived", False))
    row_packed = bool(getattr(row, "packed", False))
    tags_space = " ".join(str(tag) for tag in row_tags)
    return {
        "path": str(row_path),
        "path_q": _quote(str(row_path)),
        "rel_path": str(rel),
        "rel_path_q": _quote(str(rel)),
        "name": row_name,
        "name_q": _quote(row_name),
        "parent_path": str(row_path.parent),
        "parent_path_q": _quote(str(row_path.parent)),
        "branch": row_branch,
        "branch_q": _quote(row_branch),
        "dirty": row_dirty,
        "description": row_desc,
        "description_q": _quote(row_desc),
        "tags": ",".join(str(tag) for tag in row_tags),
        "tags_space": tags_space,
        "tags_space_q": _quote(tags_space),
        "properties": ",".join(str(prop) for prop in row_props),
        "suffix": row_suffix,
        "wip": "1" if row_wip else "0",
        "archived": "1" if row_archived else "0",
        "packed": "1" if row_packed else "0",
        "created": str(row_created or _fmt_ymd(row_created_ts)),
        "created_iso": _fmt_iso(row_created_ts),
        "created_ts": str(max(0, row_created_ts)),
        "last_modified": str(row_last or _fmt_ymd(row_last_ts)),
        "last_modified_iso": _fmt_iso(row_last_ts),
        "last_modified_ts": str(max(0, row_last_ts)),
        "last_opened": _fmt_ymd(row_opened_ts),
        "last_opened_iso": _fmt_iso(row_opened_ts),
        "last_opened_ts": str(max(0, row_opened_ts)),
        "archived_at": _fmt_ymd(row_archived_ts),
        "archived_at_iso": _fmt_iso(row_archived_ts),
        "archived_at_ts": str(max(0, row_archived_ts)),
        "size_bytes": str(max(0, row_size_bytes)),
        "size_human": _fmt_human_bytes(row_size_bytes),
        "note_path": note_path,
        "note_path_q": _quote(note_path),
    }


def build_list_context(app: Any, rows: list[ProjectRow], base_dir: Path) -> dict[str, str]:
    paths = [str(row.path) for row in rows]
    rel_paths: list[str] = []
    for row in rows:
        rel = row.path
        try:
            rel = row.path.relative_to(base_dir)
        except ValueError:
            pass
        rel_paths.append(str(rel))
    names = [str(row.name) for row in rows]
    quoted_paths = " ".join(_quote(path) for path in paths)
    return {
        "paths": " ".join(paths),
        "paths_q": quoted_paths,
        "rel_paths": " ".join(rel_paths),
        "rel_paths_q": " ".join(_quote(path) for path in rel_paths),
        "names": " ".join(names),
        "names_q": " ".join(_quote(name) for name in names),
    }


def build_filepicker_context(picked: str) -> dict[str, str]:
    value = str(picked)
    return {
        "selection": value,
        "selection_q": _quote(value),
    }


def build_always_context(app: Any, base_dir: Path) -> dict[str, str]:
    now = datetime.now().astimezone()
    archive_dir = base_dir / "_archive"
    active_rows = list(getattr(app, "active_rows", []))
    archived_rows = list(getattr(app, "archived_rows", []))
    selected = list(getattr(app, "_target_rows", lambda: [])())
    filter_text = str(getattr(app, "query", "") or "")
    home = str(Path.home())
    return {
        "base_dir": str(base_dir),
        "base_dir_q": _quote(str(base_dir)),
        "base_name": base_dir.name,
        "archive_dir": str(archive_dir),
        "archive_dir_q": _quote(str(archive_dir)),
        "active_count": str(len(active_rows)),
        "archive_count": str(len(archived_rows)),
        "wip_count": str(sum(1 for row in active_rows if bool(getattr(row, "wip", False)))),
        "count": str(len(selected)),
        "view": str(getattr(app, "view_mode", "active")),
        "filter": filter_text,
        "filter_q": _quote(filter_text),
        "now": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "now_iso": now.isoformat(timespec="seconds"),
        "now_ts": str(int(now.timestamp())),
        "today": now.strftime("%Y-%m-%d"),
        "user": str(os.environ.get("USER", "")),
        "home": home,
        "home_q": _quote(home),
    }


def render_template(text: str, *contexts: dict[str, str]) -> str:
    merged: dict[str, str] = {}
    for ctx in contexts:
        merged.update({key: str(value) for key, value in ctx.items()})
    converted = _VAR_RE.sub(lambda m: "${" + m.group(1) + "}", text)
    return Template(converted).safe_substitute(merged)


def validate_template(text: str, allowed: set[str]) -> list[str]:
    messages: list[str] = []
    for var in _VAR_RE.findall(str(text)):
        if var not in allowed:
            messages.append(f"unknown template variable: {var}")
        elif not var.endswith("_q"):
            messages.append(f"warning: unquoted template variable in command: {var}")
    return messages
