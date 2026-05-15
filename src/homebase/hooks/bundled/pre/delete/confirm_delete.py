from __future__ import annotations

from homebase.core.models import PreResult
from homebase.hooks.api import HookContext


def run(ctx: HookContext) -> PreResult | None:
    require_confirm = bool(ctx.hook.config.get("require_confirm", True))
    if not require_confirm:
        return None
    target_count = len(ctx.targets)
    answer = ctx.ask(
        prompt=f"Delete {target_count} project(s)?",
        kind="yes_no",
        default=False,
    )
    if answer == "yes":
        return None
    return PreResult(decision="cancel", reason="delete cancelled by pre-hook")
