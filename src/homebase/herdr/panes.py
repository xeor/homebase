from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

from ..core.models import PaneRef
from ..core.utils import is_under
from . import client as herdr_client
from .client import HerdrCall, HerdrError

HERDR_SOURCE = "herdr"


def _label_by_workspace(call: HerdrCall) -> dict[str, str]:
    out: dict[str, str] = {}
    for ws in call("workspace.list", {}).get("workspaces", []):
        if isinstance(ws, dict):
            wid = str(ws.get("workspace_id", ""))
            out[wid] = str(ws.get("label", "") or wid)
    return out


def _suffix_number(ident: str, marker: str) -> str:
    """``w4:t2`` with marker ``t`` -> ``2`` (the id itself when unexpected)."""
    _head, sep, tail = ident.rpartition(":" + marker)
    return tail if sep and tail.isdigit() else ident


def pane_target(pane: dict[str, Any]) -> str:
    """tmux-style ``workspace:tab.pane`` so the pane picker groups by tab."""
    workspace_id = str(pane.get("workspace_id", ""))
    tab = _suffix_number(str(pane.get("tab_id", "")), "t")
    num = _suffix_number(str(pane.get("pane_id", "")), "p")
    return f"{workspace_id}:{tab}.{num}"


def pane_command(pane: dict[str, Any], info: dict[str, Any]) -> str:
    """What runs in the pane: the recognized agent, else the foreground
    process group leader (like tmux's ``pane_current_command``)."""
    agent = str(pane.get("agent", "") or "").strip()
    if agent:
        return agent
    procs = [p for p in info.get("foreground_processes", []) if isinstance(p, dict)]
    leader = info.get("foreground_process_group_id")
    chosen = next((p for p in procs if p.get("pid") == leader), procs[0] if procs else None)
    if chosen is None:
        return ""
    name = str(chosen.get("argv0") or chosen.get("name") or "")
    return Path(name.lstrip("-")).name


def list_panes(*, call: HerdrCall = herdr_client.call) -> list[PaneRef]:
    """All panes of the herdr server, focused pane first."""
    labels = _label_by_workspace(call)
    out: list[PaneRef] = []
    for pane in call("pane.list", {}).get("panes", []):
        if not isinstance(pane, dict):
            continue
        pane_id = str(pane.get("pane_id", "")).strip()
        cwd_text = str(pane.get("foreground_cwd") or pane.get("cwd") or "").strip()
        if not pane_id or not cwd_text:
            continue
        try:
            info = call("pane.process_info", {"pane_id": pane_id}).get("process_info", {})
        except HerdrError:
            info = {}
        workspace_id = str(pane.get("workspace_id", ""))
        out.append(
            PaneRef(
                pane_id=pane_id,
                target=pane_target(pane),
                window_name=labels.get(workspace_id, workspace_id),
                command=pane_command(pane, info if isinstance(info, dict) else {}),
                cwd=Path(cwd_text),
                active=bool(pane.get("focused", False)),
                source=HERDR_SOURCE,
            )
        )
    out.sort(key=lambda p: (0 if p.active else 1, p.pane_id))
    return out


def find_panes_for_cwd(target: Path, panes: list[PaneRef]) -> list[PaneRef]:
    """Panes inside ``target``; else panes whose workspace is named after it."""
    try:
        root = target.resolve()
    except OSError:
        return []
    by_cwd: list[PaneRef] = []
    by_name: list[PaneRef] = []
    for pane in panes:
        try:
            cwd = pane.cwd.resolve()
        except OSError:
            continue
        if cwd == root or is_under(cwd, root):
            by_cwd.append(pane)
        elif pane.window_name == root.name:
            by_name.append(pane)
    return by_cwd or by_name


def focus_pane(pane_id: str, *, call: HerdrCall = herdr_client.call) -> None:
    """Focus a pane, switching workspace and tab as needed."""
    call("pane.focus", {"pane_id": pane_id})


def open_new(path: Path, kind: str, *, call: HerdrCall = herdr_client.call) -> str:
    """Open ``path`` in a new herdr tab (current workspace) or workspace.
    Returns the new pane id."""
    params: dict[str, Any] = {"cwd": str(path), "label": path.name, "focus": True}
    if kind == "workspace":
        result = call("workspace.create", params)
    else:
        workspace_id = herdr_client.current_workspace_id()
        if workspace_id:
            params["workspace_id"] = workspace_id
        result = call("tab.create", params)
    root = result.get("root_pane", {})
    return str(root.get("pane_id", "")) if isinstance(root, dict) else ""


def goto_candidates(path: Path, *, call: HerdrCall = herdr_client.call) -> list[PaneRef]:
    """Panes to jump to for ``path``, never the pane b itself runs in."""
    own = herdr_client.current_pane_id()
    return [p for p in find_panes_for_cwd(path, list_panes(call=call)) if p.pane_id != own]


def open_with_mode(
    path: Path,
    spec: dict[str, object],
    *,
    open_shell_in_dir: Callable[[Path], int],
    call: HerdrCall = herdr_client.call,
    available: Callable[[], bool] = lambda: herdr_client.socket_path() is not None,
) -> int:
    """`b open` / Enter for a herdr open profile."""
    if not available():
        if bool(spec.get("fallback_cd", True)):
            return open_shell_in_dir(path)
        print("open mode requires a running herdr", file=sys.stderr)
        return 1
    try:
        if bool(spec.get("goto_loaded", False)):
            panes = goto_candidates(path, call=call)
            if panes:
                focus_pane(panes[0].pane_id, call=call)
                return 0
        open_new(path, str(spec.get("herdr_new", "tab")), call=call)
    except HerdrError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0
