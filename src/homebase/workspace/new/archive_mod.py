from __future__ import annotations

from ..rows import archive_destination
from .base import NewContext, NewPlan


def apply_archive_modifier(plan: NewPlan, ctx: NewContext) -> NewPlan:
    """Rewrite `plan.target` to land under
    `~/base/_archive/<YYYY>/<YYYY-MM-DD>_<name>/` instead of
    `~/base/<name>/`. Updates the log kind/payload accordingly.
    Source apply()s already derive sub-paths (repo/, files) from
    `plan.target`, so they follow automatically.
    """
    old = str(plan.target)
    new_target = archive_destination(plan.target, ctx.base_dir)
    plan.target = new_target
    plan.log_kind = "migration"
    payload = dict(plan.log_payload)
    payload["archive"] = True
    payload.setdefault("source_name", plan.name)
    payload["destination"] = str(new_target)
    plan.log_payload = payload
    plan.signals = [*plan.signals, "ARCHIVE"]
    plan.steps = [step.replace(old, str(new_target)) for step in plan.steps]
    return plan
