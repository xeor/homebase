from __future__ import annotations

from typing import Any

from ..core.models import HookTarget, PreOutcome


def dispatch_pre(
    app: Any,
    *,
    event: str,
    targets: list[HookTarget],
    change: dict[str, object],
    view: str,
) -> PreOutcome:
    return PreOutcome(cancelled=False, reason="", change=dict(change))


def dispatch_post(
    app: Any,
    *,
    event: str,
    targets: list[HookTarget],
    change: dict[str, object],
    view: str,
) -> None:
    return None
