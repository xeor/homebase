from __future__ import annotations

from typing import Any, Callable

from .basic import ConfirmScreen


def confirm_destructive(
    app: Any,
    *,
    title: str,
    details: str = "",
    on_yes: Callable[[], None],
    on_no: Callable[[], None] | None = None,
) -> None:
    """Push a yes/no confirm modal in front of an action that would
    wipe state the user explicitly set or that another flow pre-
    filled. Runs ``on_yes`` on accept; ``on_no`` (or nothing) on
    decline.

    Use this wherever switching a control would silently lose
    typed/pre-filled data — source pickers, action targets, etc.
    The pattern is intentionally generic so the same modal renders
    no matter which flow invokes it.
    """

    def _on_choice(ok: bool | None) -> None:
        if ok:
            on_yes()
        elif on_no is not None:
            on_no()

    app.push_screen(ConfirmScreen(title, details), _on_choice)


__all__ = ["confirm_destructive"]
