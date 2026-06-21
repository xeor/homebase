from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any, Callable

from ..core.models import Action

SUPPORTED_BUILTINS = {"open_selected", "notes_create", "notes_open"}
_VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def _raycast_enabled(action: Action | None) -> bool:
    if action is None:
        return False
    cfg = action.raycast if isinstance(action.raycast, dict) else {}
    return bool(cfg.get("enabled", False))


def _raycast_title(action: Action) -> str:
    cfg = action.raycast if isinstance(action.raycast, dict) else {}
    title = str(cfg.get("title", "")).strip()
    return title or action.label


def _find_row(base_dir: Path, project: str, rows: list[Any]) -> Any | None:
    text = project.strip()
    if not text:
        return None
    candidate = (base_dir / text).resolve()
    for row in rows:
        path = Path(str(getattr(row, "path", ""))).resolve()
        if path == candidate or str(getattr(row, "name", "")) == text:
            return row
    return None


def _quote(value: object) -> str:
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


def _fmt_ago(ts: int, *, now_ts: int) -> str:
    if ts <= 0:
        return "never"
    delta = max(0, now_ts - int(ts))
    units = (
        ("year", 365 * 24 * 60 * 60),
        ("month", 30 * 24 * 60 * 60),
        ("week", 7 * 24 * 60 * 60),
        ("day", 24 * 60 * 60),
        ("hour", 60 * 60),
        ("minute", 60),
    )
    for label, seconds in units:
        if delta >= seconds:
            count = max(1, delta // seconds)
            suffix = "" if count == 1 else "s"
            return f"{count} {label}{suffix} ago"
    return "just now"


def _render_template(text: str, *contexts: dict[str, str]) -> str:
    merged: dict[str, str] = {}
    for ctx in contexts:
        merged.update({key: str(value) for key, value in ctx.items()})
    converted = _VAR_RE.sub(lambda m: "${" + m.group(1) + "}", text)
    return Template(converted).safe_substitute(merged)


def _relative_to_base(path: Path, base_dir: Path) -> Path:
    try:
        return path.relative_to(base_dir)
    except ValueError:
        return path


def _flag(value: object) -> str:
    return str(int(bool(value)))


def _int_attr(row: Any, name: str) -> int:
    return int(getattr(row, name, 0) or 0)


def _list_attr(row: Any, name: str) -> list[object]:
    return list(getattr(row, name, []))


def _archive_name_parts(row_name: str, archived: bool, archived_ts: int) -> tuple[str, str]:
    if not archived:
        return "", row_name
    if archived_ts <= 0:
        return "_archive/", row_name
    date_prefix = _fmt_ymd(archived_ts)
    return f"_archive/{date_prefix[:4]}/", f"{date_prefix}_{row_name}"


def _with_lowercase_keys(context: dict[str, str]) -> dict[str, str]:
    out = dict(context)
    for key, value in context.items():
        out[key.lower()] = value
    return out


def _notes_template_context(base_dir: Path, row: Any) -> dict[str, str]:
    row_path = Path(str(getattr(row, "path", "")))
    rel_path = _relative_to_base(row_path, base_dir)
    row_name = str(getattr(row, "name", row_path.name))
    archived = bool(getattr(row, "archived", False))
    archived_ts = _int_attr(row, "archived_ts")
    archive_prefix, archive_name = _archive_name_parts(row_name, archived, archived_ts)
    archive_prefixed_name = f"{archive_prefix}{archive_name}"
    restore_target = getattr(row, "restore_target", None)
    context = {
        "NAME": row_name,
        "PROJECT_NAME": row_name,
        "NAME_WITH_ARCHIVE_PREFIX": archive_prefixed_name,
        "ARCHIVE_PREFIX": archive_prefix,
        "PROJECT_PATH": str(row_path),
        "FULL_PATH": str(row_path),
        "REL_PATH": str(rel_path),
        "BASE_DIR": str(base_dir),
        "VIEW_MODE": "archive" if archived else "active",
        "BRANCH": str(getattr(row, "branch", "")),
        "DESCRIPTION": str(getattr(row, "description", "")),
        "TAGS": ",".join(str(tag) for tag in _list_attr(row, "tags")),
        "PROPERTIES": ",".join(str(prop) for prop in _list_attr(row, "properties")),
        "ARCHIVED": _flag(archived),
        "PACKED": _flag(getattr(row, "packed", False)),
        "RESTORE_TARGET": str(restore_target) if restore_target is not None else "",
        "CREATED": str(getattr(row, "created", "")),
        "MODIFIED": str(getattr(row, "last", "")),
        "ACTIVE": _fmt_ymd(_int_attr(row, "opened_ts")),
    }
    out = _with_lowercase_keys(context)
    out["NAME_WITH_ARCHIVE_PREFIX_Q"] = _quote(archive_prefixed_name)
    out["name_with_archive_prefix_q"] = out["NAME_WITH_ARCHIVE_PREFIX_Q"]
    return out


def _render_notes_template(template_text: str, context: dict[str, str]) -> str:
    return _VAR_RE.sub(lambda m: str(context.get(m.group(1), "")), template_text)


def _resolve_notes_path_for_row(
    base_dir: Path,
    row: Any,
    notes_config: dict[str, object],
) -> Path:
    template = str(notes_config.get("path_template", "")).strip()
    if not template:
        raise ValueError("notes.path_template is empty")
    context = _notes_template_context(base_dir, row)
    path_context = dict(context)
    for key, value in context.items():
        if not key.endswith("_Q"):
            continue
        raw_key = key[:-2]
        path_context[key] = context.get(raw_key, value)
    rendered = _render_notes_template(template, path_context).strip()
    if not rendered:
        raise ValueError("notes.path_template rendered to empty path")
    expanded = os.path.expandvars(rendered)
    candidate = Path(expanded).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate.resolve(strict=False)


def _build_always_context(
    base_dir: Path,
    row: Any,
    *,
    active_rows: list[Any],
    archived_rows: list[Any],
) -> dict[str, str]:
    now = datetime.now().astimezone()
    archive_dir = base_dir / "_archive"
    home = str(Path.home())
    return {
        "base_dir": str(base_dir),
        "base_dir_q": _quote(base_dir),
        "base_name": base_dir.name,
        "archive_dir": str(archive_dir),
        "archive_dir_q": _quote(archive_dir),
        "active_count": str(len(active_rows)),
        "archive_count": str(len(archived_rows)),
        "wip_count": str(
            sum(1 for item in active_rows if bool(getattr(item, "wip", False)))
        ),
        "count": "1",
        "view": "archive" if bool(getattr(row, "archived", False)) else "active",
        "filter": "",
        "filter_q": "''",
        "now": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "now_iso": now.isoformat(timespec="seconds"),
        "now_ts": str(int(now.timestamp())),
        "today": now.strftime("%Y-%m-%d"),
        "user": str(os.environ.get("USER", "")),
        "home": home,
        "home_q": _quote(home),
    }


def _note_path_text(
    base_dir: Path,
    row: Any,
    notes_config: dict[str, object],
) -> str:
    try:
        return str(_resolve_notes_path_for_row(base_dir, row, notes_config))
    except (OSError, ValueError, RuntimeError):
        return ""


def _build_per_row_context(
    base_dir: Path,
    row: Any,
    notes_config: dict[str, object],
) -> dict[str, str]:
    row_path = Path(str(getattr(row, "path", "")))
    rel = _relative_to_base(row_path, base_dir)
    note_path = _note_path_text(base_dir, row, notes_config)
    row_name = str(getattr(row, "name", row_path.name))
    row_tags = _list_attr(row, "tags")
    row_props = _list_attr(row, "properties")
    row_created_ts = _int_attr(row, "created_ts")
    row_last_ts = _int_attr(row, "last_ts")
    row_opened_ts = _int_attr(row, "opened_ts")
    row_archived_ts = _int_attr(row, "archived_ts")
    row_size_bytes = _int_attr(row, "size_bytes")
    tags_space = " ".join(str(tag) for tag in row_tags)
    return {
        "path": str(row_path),
        "path_q": _quote(row_path),
        "rel_path": str(rel),
        "rel_path_q": _quote(rel),
        "name": row_name,
        "name_q": _quote(row_name),
        "parent_path": str(row_path.parent),
        "parent_path_q": _quote(row_path.parent),
        "branch": str(getattr(row, "branch", "-")),
        "branch_q": _quote(str(getattr(row, "branch", "-"))),
        "dirty": str(getattr(row, "dirty", "")),
        "description": str(getattr(row, "description", "")),
        "description_q": _quote(str(getattr(row, "description", ""))),
        "tags": ",".join(str(tag) for tag in row_tags),
        "tags_space": tags_space,
        "tags_space_q": _quote(tags_space),
        "properties": ",".join(str(prop) for prop in row_props),
        "suffix": str(getattr(row, "suffix", "") or ""),
        "wip": _flag(getattr(row, "wip", False)),
        "archived": _flag(getattr(row, "archived", False)),
        "packed": _flag(getattr(row, "packed", False)),
        "created": str(getattr(row, "created", "") or _fmt_ymd(row_created_ts)),
        "created_iso": _fmt_iso(row_created_ts),
        "created_ts": str(max(0, row_created_ts)),
        "modified": str(getattr(row, "last", "") or _fmt_ymd(row_last_ts)),
        "modified_iso": _fmt_iso(row_last_ts),
        "modified_ts": str(max(0, row_last_ts)),
        "active": _fmt_ymd(row_opened_ts),
        "active_iso": _fmt_iso(row_opened_ts),
        "active_ts": str(max(0, row_opened_ts)),
        "archived_at": _fmt_ymd(row_archived_ts),
        "archived_at_iso": _fmt_iso(row_archived_ts),
        "archived_at_ts": str(max(0, row_archived_ts)),
        "size_bytes": str(max(0, row_size_bytes)),
        "size_human": _fmt_human_bytes(row_size_bytes),
        "note_path": note_path,
        "note_path_q": _quote(note_path),
    }


def _build_list_context(base_dir: Path, row: Any) -> dict[str, str]:
    row_path = Path(str(getattr(row, "path", "")))
    rel = row_path
    try:
        rel = row_path.relative_to(base_dir)
    except ValueError:
        pass
    name = str(getattr(row, "name", row_path.name))
    return {
        "paths": str(row_path),
        "paths_q": _quote(row_path),
        "rel_paths": str(rel),
        "rel_paths_q": _quote(rel),
        "names": name,
        "names_q": _quote(name),
    }


def _build_raycast_context(base_dir: Path, row: Any, *, now_ts: int) -> dict[str, str]:
    row_path = Path(str(getattr(row, "path", "")))
    rel = _relative_to_base(row_path, base_dir)
    row_name = str(getattr(row, "name", row_path.name))
    row_tags = [str(tag) for tag in _list_attr(row, "tags") if str(tag)]
    row_props = [str(prop) for prop in _list_attr(row, "properties") if str(prop)]
    opened_ts = _int_attr(row, "opened_ts")
    last_ts = _int_attr(row, "last_ts")
    created_ts = _int_attr(row, "created_ts")
    context = {
        "path": str(row_path),
        "rel_path": str(rel),
        "name": row_name,
        "branch": str(getattr(row, "branch", "")),
        "dirty": str(getattr(row, "dirty", "")),
        "description": str(getattr(row, "description", "")),
        "tags": ",".join(row_tags),
        "tags_space": " ".join(row_tags),
        "properties": ",".join(row_props),
        "properties_space": " ".join(row_props),
        "suffix": str(getattr(row, "suffix", "") or ""),
        "wip": _flag(getattr(row, "wip", False)),
        "created": str(getattr(row, "created", "") or _fmt_ymd(created_ts)),
        "created_iso": _fmt_iso(created_ts),
        "created_ago": _fmt_ago(created_ts, now_ts=now_ts),
        "modified": str(getattr(row, "last", "") or _fmt_ymd(last_ts)),
        "modified_iso": _fmt_iso(last_ts),
        "modified_ago": _fmt_ago(last_ts, now_ts=now_ts),
        "active": _fmt_ymd(opened_ts),
        "active_iso": _fmt_iso(opened_ts),
        "active_ago": _fmt_ago(opened_ts, now_ts=now_ts),
        "opened": _fmt_ymd(opened_ts),
        "opened_iso": _fmt_iso(opened_ts),
        "opened_ago": _fmt_ago(opened_ts, now_ts=now_ts),
        "size_human": _fmt_human_bytes(_int_attr(row, "size_bytes")),
    }
    out = _with_lowercase_keys(context)
    out["path_q"] = _quote(row_path)
    out["rel_path_q"] = _quote(rel)
    out["name_q"] = _quote(row_name)
    out["tags_space_q"] = _quote(out["tags_space"])
    return out


def _note_action_id(
    base_dir: Path,
    actions: dict[str, Action],
    row: Any,
    notes_config: dict[str, object],
) -> str | None:
    create_enabled = _raycast_enabled(actions.get("notes_create"))
    open_enabled = _raycast_enabled(actions.get("notes_open"))
    if not create_enabled and not open_enabled:
        return None
    try:
        exists = _resolve_notes_path_for_row(base_dir, row, notes_config).is_file()
    except (OSError, RuntimeError, ValueError):
        exists = False
    if exists and open_enabled:
        return "notes_open"
    if not exists and create_enabled:
        return "notes_create"
    return None


def _supported_action_ids(
    base_dir: Path,
    actions: dict[str, Action],
    row: Any,
    notes_config: dict[str, object],
) -> list[str]:
    out: list[str] = []
    for action_id, action in actions.items():
        if action_id in {"notes_create", "notes_open"}:
            continue
        if not _raycast_enabled(action):
            continue
        if action.kind == "builtin" and action_id in SUPPORTED_BUILTINS:
            out.append(action_id)
            continue
        if action.kind == "shell" and action.scope in {"target", "workspace"}:
            out.append(action_id)
    note_id = _note_action_id(base_dir, actions, row, notes_config)
    if note_id is not None:
        out.append(note_id)
    return out


def cmd_actions(
    base_dir: Path,
    project: str,
    *,
    actions: dict[str, Action],
    load_rows: Callable[[Path], tuple[list[Any], list[Any], int]],
    notes_config: dict[str, object],
) -> int:
    active, archived, _ts = load_rows(base_dir)
    rows = list(active) + list(archived)
    if not project.strip():
        payload = []
        for row in rows:
            action_payload = []
            for action_id in _supported_action_ids(base_dir, actions, row, notes_config):
                action = actions.get(action_id)
                if action is None:
                    continue
                action_payload.append({"id": action_id, "title": _raycast_title(action)})
            payload.append(
                {
                    "project": str(getattr(row, "name", "")),
                    "actions": action_payload,
                }
            )
        print(json.dumps(payload))
        return 0

    row = _find_row(base_dir, project, rows)
    if row is None:
        print(f"raycast actions: project not found: {project}", file=sys.stderr)
        return 2
    payload = []
    for action_id in _supported_action_ids(base_dir, actions, row, notes_config):
        action = actions.get(action_id)
        if action is None:
            continue
        payload.append({"id": action_id, "title": _raycast_title(action)})
    print(json.dumps(payload))
    return 0


def _row_actions_payload(
    base_dir: Path,
    row: Any,
    *,
    actions: dict[str, Action],
    notes_config: dict[str, object],
) -> list[dict[str, str]]:
    payload = []
    for action_id in _supported_action_ids(base_dir, actions, row, notes_config):
        action = actions.get(action_id)
        if action is None:
            continue
        payload.append({"id": action_id, "title": _raycast_title(action)})
    return payload


def _sort_project_rows(rows: list[Any], sort_mode: str) -> list[Any]:
    mode = str(sort_mode).strip()
    if mode == "opened":
        return sorted(
            rows,
            key=lambda row: (
                -int(getattr(row, "opened_ts", 0) or 0),
                str(getattr(row, "name", "")).lower(),
            ),
        )
    return sorted(rows, key=lambda row: str(getattr(row, "name", "")).lower())


def _secondary_templates(config: dict[str, object]) -> list[str]:
    raw = config.get("secondary_info", [])
    if isinstance(raw, str):
        text = raw.strip()
        return [text] if text else []
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _raycast_project_payload(
    base_dir: Path,
    row: Any,
    *,
    actions: dict[str, Action],
    notes_config: dict[str, object],
    raycast_config: dict[str, object],
    now_ts: int,
) -> dict[str, object]:
    info_segments: list[str] = []
    templates = _secondary_templates(raycast_config)
    if templates:
        context = _build_raycast_context(base_dir, row, now_ts=now_ts)
        for template in templates:
            rendered = _render_template(template, context).strip()
            if rendered:
                info_segments.append(rendered)
    separator = str(raycast_config.get("secondary_separator", " • "))
    subtitle = separator.join(info_segments)
    keywords: list[str] = []
    if info_segments:
        keywords = list(
            dict.fromkeys(
                info_segments + [str(tag) for tag in _list_attr(row, "tags") if str(tag)]
            )
        )
    payload: dict[str, object] = {
        "project": str(getattr(row, "name", "")),
        "actions": _row_actions_payload(
            base_dir,
            row,
            actions=actions,
            notes_config=notes_config,
        ),
    }
    if subtitle:
        payload["subtitle"] = subtitle
    if keywords:
        payload["keywords"] = keywords
    return payload


def cmd_projects(
    base_dir: Path,
    filter_expr: str,
    *,
    actions: dict[str, Action],
    load_rows: Callable[[Path], tuple[list[Any], list[Any], int]],
    notes_config: dict[str, object],
    raycast_config: dict[str, object] | None = None,
    compile_filter_expr: Callable[[str], tuple[Callable[[Any], bool], str | None]],
) -> int:
    active, _archived, _ts = load_rows(base_dir)
    rows = list(active)
    expr = filter_expr.strip()
    if expr:
        pred, err = compile_filter_expr(expr)
        if err:
            print(f"raycast projects: invalid filter: {err}", file=sys.stderr)
            return 2
        rows = [row for row in rows if pred(row)]
    config = raycast_config if isinstance(raycast_config, dict) else {}
    rows = _sort_project_rows(rows, str(config.get("sort", "name")))
    now_ts = int(datetime.now().astimezone().timestamp())
    payload = [
        _raycast_project_payload(
            base_dir,
            row,
            actions=actions,
            notes_config=notes_config,
            raycast_config=config,
            now_ts=now_ts,
        )
        for row in rows
    ]
    print(json.dumps(payload))
    return 0


def _render_shell_action(
    base_dir: Path,
    row: Any,
    action: Action,
    notes_config: dict[str, object],
    *,
    active_rows: list[Any],
    archived_rows: list[Any],
) -> str:
    command = str(action.command or "").strip()
    always_context = _build_always_context(
        base_dir,
        row,
        active_rows=active_rows,
        archived_rows=archived_rows,
    )
    if action.scope == "workspace":
        return _render_template(command, always_context)
    return _render_template(
        command,
        always_context,
        _build_per_row_context(base_dir, row, notes_config),
        _build_list_context(base_dir, row),
    )


def _run_notes_action(
    base_dir: Path,
    row: Any,
    action_id: str,
    notes_config: dict[str, object],
) -> tuple[int, str]:
    note_path = _resolve_notes_path_for_row(base_dir, row, notes_config)
    if action_id == "notes_open" and not note_path.is_file():
        return 2, "notes file not found"
    template_key = "open_command" if action_id == "notes_open" else "create_command"
    command_template = str(notes_config.get(template_key, "")).strip()
    if not command_template:
        return 2, f"notes.{template_key} is empty"
    context = _notes_template_context(base_dir, row)
    context["NOTE_PATH"] = str(note_path)
    context["note_path"] = str(note_path)
    context["NOTE_PATH_Q"] = _quote(note_path)
    context["note_path_q"] = context["NOTE_PATH_Q"]
    command = _render_notes_template(command_template, context).strip()
    subprocess.Popen(  # noqa: S603 - user-configured action command
        ["/bin/sh", "-lc", command],
        cwd=str(base_dir),
    )
    return 0, command


def cmd_run(
    base_dir: Path,
    project: str,
    action_id: str,
    *,
    actions: dict[str, Action],
    load_rows: Callable[[Path], tuple[list[Any], list[Any], int]],
    notes_config: dict[str, object],
    open_project: Callable[[Path, str], int],
) -> int:
    active, archived, _ts = load_rows(base_dir)
    row = _find_row(base_dir, project, list(active) + list(archived))
    if row is None:
        print(f"raycast run: project not found: {project}", file=sys.stderr)
        return 2
    if action_id not in _supported_action_ids(base_dir, actions, row, notes_config):
        print(f"raycast run: unsupported or disabled action: {action_id}", file=sys.stderr)
        return 2
    if action_id == "open_selected":
        return open_project(base_dir, str(getattr(row, "name", project)))
    if action_id in {"notes_create", "notes_open"}:
        rc, message = _run_notes_action(base_dir, row, action_id, notes_config)
        if message:
            print(message)
        return rc
    action = actions.get(action_id)
    if action is None or action.kind != "shell":
        print(f"raycast run: unsupported action kind: {action_id}", file=sys.stderr)
        return 2
    command = _render_shell_action(
        base_dir,
        row,
        action,
        notes_config,
        active_rows=list(active),
        archived_rows=list(archived),
    )
    if not command:
        print(f"raycast run: empty command: {action_id}", file=sys.stderr)
        return 2
    subprocess.Popen(  # noqa: S603 - user-configured action command
        ["/bin/sh", "-lc", command],
        cwd=str(base_dir),
    )
    print(command)
    return 0
