from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


def _sqlite_recent_paths(query: dict[str, object], *, base_dir: Path) -> list[Path]:
    db_path_raw = str(query.get("db_path", "")).strip()
    if not db_path_raw:
        return []
    db_path = Path(db_path_raw).expanduser()
    table = str(query.get("table", "ItemTable")).strip() or "ItemTable"
    value_column = str(query.get("value_column", "value")).strip() or "value"
    where_like = str(query.get("where_like", "%file://%")).strip() or "%file://%"
    sql = f"select {value_column} from {table} where {value_column} like ?"
    out: list[Path] = []
    try:
        con = sqlite3.connect(str(db_path))
        try:
            rows = con.execute(sql, (where_like,)).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return []
    for (value,) in rows:
        text = str(value or "")
        if not text:
            continue
        try:
            payload = json.loads(text)
            text = json.dumps(payload)
        except json.JSONDecodeError:
            pass
        cursor = 0
        while True:
            idx = text.find("file://", cursor)
            if idx < 0:
                break
            end = idx + 7
            while end < len(text) and text[end] not in {'"', "'", " ", "\n", "\t", ",", "}"}:
                end += 1
            uri = text[idx:end]
            cursor = end
            parsed = urlparse(uri)
            if parsed.scheme != "file":
                continue
            p = Path(unquote(parsed.path or "")).expanduser()
            if p.as_posix().strip():
                out.append(p)
    return out


def evaluate_query_paths(app: Any, query: dict[str, object]) -> set[Path]:
    qtype = str(query.get("type", "")).strip()
    if qtype == "tmux_open_panes":
        return {p for p, n in app.open_pane_count_by_project.items() if int(n) > 0}
    if qtype == "tmux_editor_commands":
        commands = {
            str(cmd).strip().lower()
            for cmd in query.get("commands", [])
            if str(cmd).strip()
        }
        out: set[Path] = set()
        for path, panes in app.open_panes_by_project.items():
            for pane in panes:
                cmd = str(getattr(pane, "command", "")).strip().lower()
                if cmd in commands:
                    out.add(path)
                    break
        return out
    if qtype == "sqlite_recent_paths":
        roots = {row.path.resolve() for row in (app.active_rows + app.archived_rows)}
        out: set[Path] = set()
        for candidate in _sqlite_recent_paths(query, base_dir=app.base_dir):
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            for root in roots:
                try:
                    resolved.relative_to(root)
                    out.add(root)
                    break
                except ValueError:
                    continue
        return out
    return set()


def evaluate_query_match(app: Any, row: Any, query: dict[str, object]) -> bool:
    qtype = str(query.get("type", "")).strip()
    if qtype == "packed_archive":
        return bool(getattr(row, "packed", False))
    if qtype == "metadata_health":
        level = str(query.get("level", "")).strip().lower()
        if level not in {"warning", "error"}:
            return False
        cached = app.metadata_health_cache.get(row.path)
        if cached is None:
            return False
        if cache_due(float(cached[1])):
            return False
        health_level = str(cached[0]).strip().lower()
        return health_level == level
    if qtype in {"tmux_open_panes", "tmux_editor_commands", "sqlite_recent_paths"}:
        return row.path in evaluate_query_paths(app, query)
    return False


def cache_due(expires_at: float) -> bool:
    return time.time() >= expires_at
