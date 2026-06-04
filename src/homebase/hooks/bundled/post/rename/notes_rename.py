from __future__ import annotations

import subprocess
from pathlib import Path

from ....api import HookContext


def run(ctx: HookContext) -> None:
    if not ctx.targets:
        return
    old_raw = ctx.change.get("old_note_path")
    new_raw = ctx.change.get("new_note_path")
    cmd_raw = ctx.change.get("rendered_note_cmd")
    if not isinstance(old_raw, (str, Path)) or not isinstance(new_raw, (str, Path)):
        return
    old_note_path = Path(old_raw)
    new_note_path = Path(new_raw)
    rendered = str(cmd_raw or "").strip()
    if old_note_path == new_note_path:
        return
    try:
        if not old_note_path.exists() or not old_note_path.is_file():
            return
    except OSError:
        return
    if rendered:
        proc = subprocess.run(
            ["sh", "-lc", rendered],
            cwd=str(ctx.base_dir),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            err = (proc.stderr or "").strip() or f"exit={proc.returncode}"
            ctx.notify(f"note rename command failed: {err}", "warn")
            return
    else:
        new_note_path.parent.mkdir(parents=True, exist_ok=True)
        old_note_path.rename(new_note_path)
    ctx.add_event(ctx.targets[0].path, "note_rename", {"from": str(old_note_path), "to": str(new_note_path)})
