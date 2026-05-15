from __future__ import annotations

from ....api import HookContext

DESCRIPTION = "Show a status notification after project deletion."


def run(ctx: HookContext) -> None:
    level = str(ctx.hook.config.get("level", "info") or "info")
    removed_raw = ctx.change.get("removed_paths")
    removed = list(removed_raw) if isinstance(removed_raw, list) else []
    count = len(removed) or len(ctx.targets)
    ctx.notify(f"deleted {count} project(s)", level)
