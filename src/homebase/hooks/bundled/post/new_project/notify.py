from __future__ import annotations

from pathlib import Path

from ....api import HookContext

DESCRIPTION = "Show a status notification after a new project is created."


def run(ctx: HookContext) -> None:
    level = str(ctx.hook.config.get("level", "info") or "info")
    created_raw = ctx.change.get("created_path")
    name = "?"
    if created_raw is not None:
        name = Path(str(created_raw)).name or str(created_raw)
    source = str(ctx.change.get("source") or "")
    template = ctx.change.get("template")
    extra: list[str] = []
    if source:
        extra.append(f"source={source}")
    if template:
        extra.append(f"template={template}")
    suffix = f" ({', '.join(extra)})" if extra else ""
    ctx.notify(f"new project: {name}{suffix}", level)
