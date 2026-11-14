"""herdr space layout <-> saved project layout.

A saved layout is every tab of a space: label, split tree (direction, ratio),
pane cwd relative to the project, the command running in each pane, focused
pane and zoom. herdr's ``layout.export`` / ``layout.apply`` do the tree; the
commands are typed into the new panes, never run.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Any

from ..core.constants import HERDR_LAYOUT_VERSION
from ..core.utils import is_under
from . import client as herdr_client
from .client import HerdrCall, HerdrError

_TAB_NUMBER_RE = re.compile(r"^\[\d+\] ?")

Node = dict[str, Any]


def clean_tab_label(label: object) -> str | None:
    """``[2] k9s`` -> ``k9s`` (corex tab-numbers plugin). Unnamed tabs (herdr
    reports the bare position, or ``[n]``) -> None."""
    text = _TAB_NUMBER_RE.sub("", str(label or "")).strip()
    if not text or text.isdigit():
        return None
    return text


def project_root(path: Path, base_dir: Path) -> Path | None:
    """``<base>/<p>`` for any path inside it (a herdr space = one project)."""
    base = base_dir.resolve()
    try:
        rel = path.resolve().relative_to(base)
    except ValueError:
        return None
    if not rel.parts:
        return None
    return base / rel.parts[0]


def leader_argv(info: dict[str, Any]) -> list[str] | None:
    """argv of the pane's foreground process group leader; None when the
    shell itself is in the foreground."""
    leader = info.get("foreground_process_group_id")
    if leader is None or leader == info.get("shell_pid"):
        return None
    for proc in info.get("foreground_processes", []):
        if not isinstance(proc, dict) or proc.get("pid") != leader:
            continue
        argv = proc.get("argv")
        if isinstance(argv, list) and argv and all(isinstance(a, str) for a in argv):
            return list(argv)
    return None


def leaves(node: Node) -> list[Node]:
    """Pane nodes in tree order (first before second)."""
    if node.get("type") == "split":
        return [*leaves(node["first"]), *leaves(node["second"])]
    return [node]


def _relative_cwd(cwd: object, root: Path) -> str:
    if not cwd:
        return "."
    path = Path(str(cwd))
    if path == root or is_under(path, root):
        rel = path.resolve().relative_to(root.resolve())
        return str(rel) if rel.parts else "."
    return str(path)


def _absolute_cwd(cwd: object, root: Path) -> Path:
    path = Path(str(cwd or "."))
    full = path if path.is_absolute() else root / path
    return full if full.is_dir() else root


def saved_node(node: Node, root: Path, commands: dict[str, list[str]]) -> Node:
    """herdr export tree -> saved tree (relative cwd, command, no pane ids)."""
    if node.get("type") == "split":
        return {
            "type": "split",
            "direction": str(node["direction"]),
            "ratio": round(float(node["ratio"]), 4),
            "first": saved_node(node["first"], root, commands),
            "second": saved_node(node["second"], root, commands),
        }
    out: Node = {"type": "pane", "cwd": _relative_cwd(node.get("cwd"), root)}
    if node.get("label"):
        out["label"] = str(node["label"])
    command = commands.get(str(node.get("pane_id", "")))
    if command:
        out["command"] = command
    return out


def apply_node(node: Node, root: Path) -> Node:
    """Saved tree -> herdr ``layout.apply`` tree (absolute cwd, no command)."""
    if node.get("type") == "split":
        return {
            "type": "split",
            "direction": str(node["direction"]),
            "ratio": float(node["ratio"]),
            "first": apply_node(node["first"], root),
            "second": apply_node(node["second"], root),
        }
    out: Node = {"type": "pane", "cwd": str(_absolute_cwd(node.get("cwd"), root))}
    if node.get("label"):
        out["label"] = str(node["label"])
    return out


def is_trivial(layout: dict[str, Any]) -> bool:
    """One tab, one pane, nothing running: not worth saving (and never
    allowed to replace a real saved layout)."""
    tabs = layout.get("tabs", [])
    if len(tabs) != 1:
        return False
    panes = leaves(tabs[0]["root"])
    return len(panes) == 1 and not panes[0].get("command")


def summary(layout: dict[str, Any]) -> str:
    tabs = layout.get("tabs", [])
    panes = sum(len(leaves(t["root"])) for t in tabs)
    return f"{len(tabs)} tab{'s' if len(tabs) != 1 else ''}, {panes} pane{'s' if panes != 1 else ''}"


def validate(layout: object) -> dict[str, Any]:
    """Raise ValueError unless ``layout`` is a saved layout this version reads."""
    if not isinstance(layout, dict) or layout.get("version") != HERDR_LAYOUT_VERSION:
        raise ValueError(f"not a version {HERDR_LAYOUT_VERSION} herdr layout")
    tabs = layout.get("tabs")
    if not isinstance(tabs, list) or not tabs:
        raise ValueError("herdr layout has no tabs")
    for tab in tabs:
        if not isinstance(tab, dict) or not isinstance(tab.get("root"), dict):
            raise ValueError("herdr layout tab without a root")
        _validate_node(tab["root"])
    return layout


def _validate_node(node: Node) -> None:
    kind = node.get("type")
    if kind == "split":
        if node.get("direction") not in ("right", "down"):
            raise ValueError(f"bad split direction {node.get('direction')!r}")
        float(node["ratio"])
        _validate_node(node["first"])
        _validate_node(node["second"])
        return
    if kind != "pane":
        raise ValueError(f"bad layout node type {kind!r}")
    command = node.get("command")
    if command is not None and not (
        isinstance(command, list) and all(isinstance(a, str) for a in command)
    ):
        raise ValueError("pane command must be a list of strings")


# --- herdr I/O ---------------------------------------------------------------


def _sort_key(pane_id: str) -> tuple[int, str]:
    # Pane ids grow with creation; same length compares as plain strings.
    return (len(pane_id), pane_id)


def workspace_tabs(workspace_id: str, *, call: HerdrCall) -> list[dict[str, Any]]:
    tabs = call("tab.list", {"workspace_id": workspace_id}).get("tabs", [])
    return [t for t in tabs if isinstance(t, dict) and t.get("workspace_id") == workspace_id]


def workspace_panes(workspace_id: str, *, call: HerdrCall) -> list[dict[str, Any]]:
    panes = call("pane.list", {"workspace_id": workspace_id}).get("panes", [])
    return [p for p in panes if isinstance(p, dict) and p.get("workspace_id") == workspace_id]


def first_pane_cwd(workspace_id: str, *, call: HerdrCall) -> Path | None:
    """cwd of the space's pane 1: oldest pane of the first tab (as corex new.sh)."""
    tabs = workspace_tabs(workspace_id, call=call)
    if not tabs:
        return None
    first_tab = tabs[0].get("tab_id")
    panes = [p for p in workspace_panes(workspace_id, call=call) if p.get("tab_id") == first_tab]
    if not panes:
        return None
    pane = min(panes, key=lambda p: _sort_key(str(p.get("pane_id", ""))))
    cwd = pane.get("cwd")
    return Path(str(cwd)) if cwd else None


def is_fresh(workspace_id: str, *, call: HerdrCall) -> bool:
    """One tab with one pane: a space that was just opened."""
    return (
        len(workspace_tabs(workspace_id, call=call)) == 1
        and len(workspace_panes(workspace_id, call=call)) == 1
    )


def _pane_commands(panes: list[dict[str, Any]], *, call: HerdrCall) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for pane in panes:
        pane_id = str(pane.get("pane_id", ""))
        try:
            info = call("pane.process_info", {"pane_id": pane_id}).get("process_info", {})
        except HerdrError:
            continue
        argv = leader_argv(info) if isinstance(info, dict) else None
        if argv:
            out[pane_id] = argv
    return out


def export_space(workspace_id: str, root: Path, *, call: HerdrCall) -> dict[str, Any]:
    """The whole space as a saved layout."""
    tabs = workspace_tabs(workspace_id, call=call)
    commands = _pane_commands(workspace_panes(workspace_id, call=call), call=call)
    active = call("workspace.get", {"workspace_id": workspace_id}).get("workspace", {})
    active_tab = active.get("active_tab_id") if isinstance(active, dict) else None
    saved_tabs: list[dict[str, Any]] = []
    focused_tab = 0
    for index, tab in enumerate(tabs):
        exported = call("layout.export", {"tab_id": tab["tab_id"]}).get("layout", {})
        tree = saved_node(exported["root"], root, commands)
        ids = [str(p.get("pane_id", "")) for p in leaves(exported["root"])]
        focused = str(exported.get("focused_pane_id", ""))
        entry: dict[str, Any] = {
            "label": clean_tab_label(tab.get("label")),
            "root": tree,
            "focused": ids.index(focused) if focused in ids else 0,
            "zoomed": bool(exported.get("zoomed", False)),
        }
        saved_tabs.append(entry)
        if tab.get("tab_id") == active_tab:
            focused_tab = index
    return {
        "version": HERDR_LAYOUT_VERSION,
        "project": root.name,
        "focused_tab": focused_tab,
        "tabs": saved_tabs,
    }


def apply_space(
    layout: dict[str, Any],
    workspace_id: str,
    root: Path,
    *,
    call: HerdrCall,
) -> list[str]:
    """Add the saved tabs to the space (after its existing tabs), type each
    pane's command without running it, restore zoom and focus. Returns the
    new tab ids in saved order."""
    new_tabs: list[str] = []
    focus_panes: list[str] = []
    for tab in layout["tabs"]:
        params: dict[str, Any] = {
            "workspace_id": workspace_id,
            "root": apply_node(tab["root"], root),
            "focus": False,
        }
        if tab.get("label"):
            params["tab_label"] = str(tab["label"])
        result = call("layout.apply", params).get("layout", {})
        created = leaves(result["root"])
        for saved, new in zip(leaves(tab["root"]), created, strict=True):
            command = saved.get("command")
            if command:
                call("pane.send_text", {"pane_id": new["pane_id"], "text": shlex.join(command)})
        index = int(tab.get("focused", 0))
        focus_pane = str(created[index if 0 <= index < len(created) else 0]["pane_id"])
        if tab.get("zoomed"):
            call("pane.zoom", {"pane_id": focus_pane, "mode": "on"})
        new_tabs.append(str(result["tab_id"]))
        focus_panes.append(focus_pane)
    index = int(layout.get("focused_tab", 0))
    index = index if 0 <= index < len(focus_panes) else 0
    for pane_id in (*focus_panes, focus_panes[index]):
        # Each tab's focused pane, the focused tab last.
        call("pane.focus", {"pane_id": pane_id})
    return new_tabs


def current_context() -> tuple[str, str, str]:
    """(workspace, tab, pane) of the pane this process runs in; empty outside herdr."""
    if not herdr_client.is_inside_herdr():
        return "", "", ""
    return (
        herdr_client.current_workspace_id(),
        os.environ.get("HERDR_TAB_ID", "").strip(),
        herdr_client.current_pane_id(),
    )
