"""`raycast.json`: the Raycast project list, prebuilt by `b daemon` so the
extension reads a file instead of starting b on every open."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from ..cache.api import cache_load_rows
from ..config.prefs import load_actions, load_notes_config, load_raycast_config
from ..config.store import clear_global_config_cache
from ..core.constants import (
    BUILTIN_ACTIONS,
    GLOBAL_CONFIG_FILE_NAME,
    HOMEBASE_DIR_NAME,
    RAYCAST_SNAPSHOT_FILE_NAME,
    RAYCAST_SNAPSHOT_MAX_AGE_S,
    RAYCAST_SNAPSHOT_VERSION,
    RUNTIME_DIR_NAME,
    discover_tab_actions,
)
from . import raycast as raycast_cmd

SNAPSHOT_ERRORS = (OSError, sqlite3.Error, TypeError, ValueError)


def snapshot_path(base_dir: Path) -> Path:
    return base_dir / HOMEBASE_DIR_NAME / RUNTIME_DIR_NAME / RAYCAST_SNAPSHOT_FILE_NAME


# Config file mtime the cached config was read at, per base. The config is
# cached for the life of the process; the daemon lives long, so it re-reads
# the file when it changes.
_CONFIG_MTIMES: dict[Path, int] = {}


def _reload_config_if_changed(base_dir: Path) -> None:
    try:
        mtime = (base_dir / HOMEBASE_DIR_NAME / GLOBAL_CONFIG_FILE_NAME).stat().st_mtime_ns
    except OSError:
        mtime = 0
    if _CONFIG_MTIMES.get(base_dir) != mtime:
        clear_global_config_cache(base_dir)
        _CONFIG_MTIMES[base_dir] = mtime


def build_snapshot(base_dir: Path, *, now: float | None = None) -> dict[str, object]:
    _reload_config_if_changed(base_dir)
    builtins = dict(BUILTIN_ACTIONS)
    builtins.update(discover_tab_actions())
    projects = raycast_cmd.projects_payload(
        base_dir,
        actions=load_actions(base_dir, builtins=builtins),
        load_rows=cache_load_rows,
        notes_config=load_notes_config(base_dir),
        raycast_config=load_raycast_config(base_dir),
    )
    return {
        "version": RAYCAST_SNAPSHOT_VERSION,
        "generated_ts": time.time() if now is None else now,
        "base_dir": str(base_dir),
        "projects": projects,
    }


def write_snapshot(base_dir: Path, snapshot: dict[str, object]) -> Path:
    path = snapshot_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(snapshot))
    tmp.replace(path)
    return path


def refresh_snapshot(base_dir: Path, last_key: str | None) -> str:
    """Rebuild the project list; write it when it changed since ``last_key``
    or the file is RAYCAST_SNAPSHOT_MAX_AGE_S old (so subtitles like
    "5 minutes ago" stay right). Returns the key of what is on disk.
    File mtimes cannot tell: reading the cache touches the database."""
    snapshot = build_snapshot(base_dir)
    key = json.dumps(snapshot["projects"], sort_keys=True)
    if key == last_key:
        try:
            age = time.time() - snapshot_path(base_dir).stat().st_mtime
        except OSError:
            age = RAYCAST_SNAPSHOT_MAX_AGE_S
        if age < RAYCAST_SNAPSHOT_MAX_AGE_S:
            return key
    write_snapshot(base_dir, snapshot)
    return key
