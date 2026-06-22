from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..core.constants import (
    HOMEBASE_DIR_NAME,
    RUNTIME_DIR_NAME,
    TMUX_CONTEXTS_FILE_NAME,
)
from .core import tmux_socket_path_from_env

TMUX_CONTEXT_TTL_S = 30.0


def registry_path(base_dir: Path) -> Path:
    return (
        base_dir
        / HOMEBASE_DIR_NAME
        / RUNTIME_DIR_NAME
        / TMUX_CONTEXTS_FILE_NAME
    )


def _instance_id() -> str:
    pane = os.environ.get("TMUX_PANE", "").strip()
    suffix = pane if pane else "no-pane"
    return f"{os.getpid()}:{suffix}"


def _load(path: Path) -> dict[str, dict[str, object]]:
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    contexts = raw.get("contexts", {})
    if not isinstance(contexts, dict):
        return {}
    out: dict[str, dict[str, object]] = {}
    for key, value in contexts.items():
        if isinstance(value, dict):
            out[str(key)] = dict(value)
    return out


def _store(path: Path, contexts: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"contexts": contexts}, sort_keys=True, indent=2))
    tmp.replace(path)


def _updated_at(context: dict[str, object]) -> float:
    value = context.get("updated_at", 0.0)
    if isinstance(value, (int, float, str)):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _is_fresh(context: dict[str, object], now: float, ttl_s: float) -> bool:
    socket_path = str(context.get("socket_path", "")).strip()
    return bool(socket_path) and _updated_at(context) + ttl_s >= now


def _pane_payload(pane: object) -> dict[str, object]:
    cwd = getattr(pane, "cwd", "")
    return {
        "pane_id": str(getattr(pane, "pane_id", "")).strip(),
        "target": str(getattr(pane, "target", "")).strip(),
        "window_name": str(getattr(pane, "window_name", "")).strip(),
        "command": str(getattr(pane, "command", "")).strip(),
        "cwd": str(cwd),
        "active": bool(getattr(pane, "active", False)),
    }


def _project_panes_payload(
    project_panes: Mapping[Path, Sequence[object]] | None,
) -> dict[str, list[dict[str, object]]]:
    if not project_panes:
        return {}
    out: dict[str, list[dict[str, object]]] = {}
    for path, panes in project_panes.items():
        payloads = [
            payload
            for payload in (_pane_payload(pane) for pane in panes)
            if payload["pane_id"] and payload["target"]
        ]
        if payloads:
            out[str(path.resolve())] = payloads
    return out


def register_current_tmux_context(
    base_dir: Path,
    *,
    open_profile: str = "",
    project_panes: Mapping[Path, Sequence[object]] | None = None,
    now: float | None = None,
) -> None:
    socket_path = tmux_socket_path_from_env()
    if not socket_path:
        return
    ts = time.time() if now is None else now
    path = registry_path(base_dir)
    contexts = {
        key: value
        for key, value in _load(path).items()
        if _is_fresh(value, ts, TMUX_CONTEXT_TTL_S)
    }
    contexts[_instance_id()] = {
        "pid": os.getpid(),
        "socket_path": socket_path,
        "tmux": os.environ.get("TMUX", ""),
        "tmux_pane": os.environ.get("TMUX_PANE", ""),
        "open_profile": open_profile,
        "project_panes": _project_panes_payload(project_panes),
        "updated_at": ts,
    }
    try:
        _store(path, contexts)
    except OSError:
        return


def unregister_current_tmux_context(base_dir: Path) -> None:
    path = registry_path(base_dir)
    contexts = _load(path)
    contexts.pop(_instance_id(), None)
    try:
        _store(path, contexts)
    except OSError:
        return


def load_active_tmux_context(
    base_dir: Path, *, now: float | None = None
) -> dict[str, Any] | None:
    contexts = load_tmux_contexts(base_dir, now=now)
    return contexts[0] if contexts else None


def load_tmux_contexts(
    base_dir: Path, *, now: float | None = None
) -> list[dict[str, Any]]:
    ts = time.time() if now is None else now
    contexts = [
        dict(context)
        for context in _load(registry_path(base_dir)).values()
        if _is_fresh(context, ts, TMUX_CONTEXT_TTL_S)
    ]
    contexts.sort(key=_updated_at, reverse=True)
    return contexts
