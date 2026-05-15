from __future__ import annotations

from ....api import HookContext

DESCRIPTION = "Show a status notification after tag changes."


def run(ctx: HookContext) -> None:
    level = str(ctx.hook.config.get("level", "info") or "info")
    plan_raw = ctx.change.get("plan")
    plan = plan_raw if isinstance(plan_raw, dict) else {}
    added = sorted(tag for tag, op in plan.items() if str(op) == "add")
    removed = sorted(tag for tag, op in plan.items() if str(op) == "remove")
    parts: list[str] = []
    if added:
        parts.append(f"+{','.join(added)}")
    if removed:
        parts.append(f"-{','.join(removed)}")
    summary = " ".join(parts) if parts else "no tag changes"
    ctx.notify(f"tags on {len(ctx.targets)} project(s): {summary}", level)
