"""`b herdr save|load`: a project's herdr layout in
``<project>/.base-state/herdr-layout.json`` (herdr/layout.py).

Save never replaces a saved layout before the space was asked about it
(``load --ask``), never while a load runs, and never with a trivial layout.
The previous file is kept as ``herdr-layout.prev.json``.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Callable

from ..core import prompting
from ..core.constants import (
    HERDR_LAYOUT_FILE,
    HERDR_LAYOUT_LOADING_MAX_S,
    HERDR_LAYOUT_STATE_DIR,
)
from ..herdr import client as herdr_client
from ..herdr import layout as herdr_layout
from ..herdr.client import HerdrCall, HerdrError

STATE_LOADING = "loading"
STATE_DONE = "done"

Prompt = Callable[..., str | None]


def layout_path(root: Path) -> Path:
    return root / HERDR_LAYOUT_FILE


def default_state_dir() -> Path:
    return Path(HERDR_LAYOUT_STATE_DIR).expanduser()


def space_state(state_dir: Path, workspace_id: str) -> str | None:
    """``loading`` / ``done`` once the space was asked; None before."""
    try:
        return (state_dir / workspace_id).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None


def set_space_state(state_dir: Path, workspace_id: str, value: str) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / workspace_id).write_text(value + "\n", encoding="utf-8")


def _is_loading(state_dir: Path, workspace_id: str, now: float) -> bool:
    if space_state(state_dir, workspace_id) != STATE_LOADING:
        return False
    age = now - (state_dir / workspace_id).stat().st_mtime
    return age < HERDR_LAYOUT_LOADING_MAX_S


def read_layout(path: Path) -> dict[str, Any]:
    return herdr_layout.validate(json.loads(path.read_text(encoding="utf-8")))


def write_layout(path: Path, layout: dict[str, Any]) -> bool:
    """Write when changed (atomic). The replaced file becomes ``*.prev.json``."""
    text = json.dumps(layout, indent=2, ensure_ascii=False) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        path.replace(path.with_name(path.stem + ".prev.json"))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
    return True


def save_space(
    workspace_id: str,
    base_dir: Path,
    *,
    call: HerdrCall,
    state_dir: Path,
    now: float,
) -> str:
    """Save one space when it is a project; returns what happened."""
    cwd = herdr_layout.first_pane_cwd(workspace_id, call=call)
    root = herdr_layout.project_root(cwd, base_dir) if cwd else None
    if root is None:
        return "skip: not a project"
    if _is_loading(state_dir, workspace_id, now):
        return "skip: loading"
    path = layout_path(root)
    existed = path.is_file()
    if existed and space_state(state_dir, workspace_id) is None:
        return f"skip: {root.name} not asked yet (b herdr load --ask)"
    layout = herdr_layout.export_space(workspace_id, root, call=call)
    if herdr_layout.is_trivial(layout):
        return f"skip: {root.name} trivial"
    if write_layout(path, layout):
        if not existed:
            # This space made the file: it owns it (no ask needed to keep saving).
            set_space_state(state_dir, workspace_id, STATE_DONE)
        return f"saved {root.name} ({herdr_layout.summary(layout)})"
    return f"unchanged {root.name}"


def _prune_states(state_dir: Path, live: set[str]) -> None:
    if not state_dir.is_dir():
        return
    for entry in state_dir.iterdir():
        if entry.is_file() and entry.name not in live:
            entry.unlink()


def cmd_herdr_save(
    base_dir: Path,
    workspace_id: str = "",
    all_spaces: bool = False,
    *,
    call: HerdrCall = herdr_client.call,
    state_dir: Path | None = None,
) -> int:
    sdir = state_dir or default_state_dir()
    try:
        if all_spaces:
            spaces = call("workspace.list", {}).get("workspaces", [])
            targets = [str(w["workspace_id"]) for w in spaces if isinstance(w, dict)]
            _prune_states(sdir, set(targets))
        else:
            target = workspace_id or herdr_layout.current_context()[0]
            if not target:
                print("b herdr save: not inside a herdr pane (use --workspace or --all)", file=sys.stderr)
                return 1
            targets = [target]
    except HerdrError as exc:
        print(f"b herdr save: {exc}", file=sys.stderr)
        return 1
    rc = 0
    for target in targets:
        try:
            status = save_space(target, base_dir, call=call, state_dir=sdir, now=time.time())
        except (HerdrError, OSError, KeyError, ValueError) as exc:
            print(f"{target}: error: {exc}", file=sys.stderr)
            rc = 1
            continue
        print(f"{target}: {status}")
    return rc


def _ask(root: Path, layout: dict[str, Any], prompt: Prompt) -> bool:
    # Runs from fish's fish_prompt hook: the tty is not in line mode there.
    with prompting.line_mode_tty():
        answer = prompt(
            f"Load saved herdr layout for {root.name} ({herdr_layout.summary(layout)})? [Y/n] ",
            default="y",
            non_interactive_default="n",
        )
    # [Y/n]: Enter is yes.
    return answer is not None and answer.strip().lower() in ("", "y", "yes")


def cmd_herdr_load(
    base_dir: Path,
    dir_path: str = ".",
    ask: bool = False,
    *,
    call: HerdrCall = herdr_client.call,
    state_dir: Path | None = None,
    prompt: Prompt = prompting.prompt_readline,
) -> int:
    """Load the project's saved layout into the current space. ``--ask``
    (fish, first prompt in a project): only for a fresh, never asked space,
    and only after a yes. A fresh space's start tab is closed afterwards."""
    sdir = state_dir or default_state_dir()
    workspace_id, tab_id, _pane = herdr_layout.current_context()
    if not workspace_id:
        print("b herdr load: not inside a herdr pane", file=sys.stderr)
        return 1
    root = herdr_layout.project_root(Path(dir_path), base_dir)
    path = layout_path(root) if root else None
    if root is None or path is None or not path.is_file():
        if ask:
            return 0
        print(f"b herdr load: no saved layout for {Path(dir_path).resolve()}", file=sys.stderr)
        return 1
    try:
        layout = read_layout(path)
        if ask and space_state(sdir, workspace_id) is not None:
            return 0
        fresh = herdr_layout.is_fresh(workspace_id, call=call)
    except (OSError, ValueError, HerdrError) as exc:
        print(f"b herdr load: {path}: {exc}", file=sys.stderr)
        return 1
    if ask and (not fresh or not _ask(root, layout, prompt)):
        set_space_state(sdir, workspace_id, STATE_DONE)
        return 0
    set_space_state(sdir, workspace_id, STATE_LOADING)
    try:
        herdr_layout.apply_space(layout, workspace_id, root, call=call)
    except (HerdrError, KeyError, ValueError) as exc:
        set_space_state(sdir, workspace_id, STATE_DONE)
        print(f"b herdr load: {exc}", file=sys.stderr)
        return 1
    set_space_state(sdir, workspace_id, STATE_DONE)
    if fresh and tab_id:
        # Closes this pane (and this process): always the last step.
        try:
            call("tab.close", {"tab_id": tab_id})
        except HerdrError as exc:
            print(f"b herdr load: closing the start tab: {exc}", file=sys.stderr)
            return 1
    return 0
