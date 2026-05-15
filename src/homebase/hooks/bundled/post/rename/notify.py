from __future__ import annotations

from ....api import HookContext

DESCRIPTION = "Show a status notification after a project rename."


def run(ctx: HookContext) -> None:
    level = str(ctx.hook.config.get("level", "info") or "info")
    old_name = str(ctx.change.get("old_name") or "?")
    new_name = str(ctx.change.get("new_name") or "?")
    ctx.notify(f"renamed: {old_name} -> {new_name}", level)
