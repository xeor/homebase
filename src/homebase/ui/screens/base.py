from __future__ import annotations

from typing import TypeVar

from textual.screen import ModalScreen
from textual.widgets import Static

ScreenResultT = TypeVar("ScreenResultT")


class BaseModalScreen(ModalScreen[ScreenResultT]):
    """Shared look for the project's small modal dialogs (notifications,
    single-field inputs, errors).

    Concrete screens compose their body inside ``Vertical(id="modal_box")``
    and end it with the result of :meth:`hotkey_footer`. Panel size is
    roughly 1/2 of the screen with a unified border, surface background,
    and a horizontal-pill hotkey list at the bottom.

    Subclasses can override the border color by adding a CSS rule like
    ``ConfirmScreen #modal_box { border: round $warning; }``.

    For list-heavy or info-dense dialogs (confirmations with long
    details, pickers, planners, multi-line editors), subclass
    :class:`LargeModalScreen` instead — same contract, 4/5 × 4/5 panel.
    """

    DEFAULT_CSS = """
    BaseModalScreen {
        align: center middle;
    }
    BaseModalScreen #modal_box {
        width: 50%;
        height: 50%;
        min-width: 60;
        min-height: 12;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    BaseModalScreen #modal_body {
        height: 1fr;
    }
    BaseModalScreen #modal_hotkeys {
        height: auto;
        color: $text-muted;
        border-top: solid $surface-lighten-1;
        padding: 1 0 0 0;
        margin: 1 0 0 0;
    }
    """

    @staticmethod
    def hotkey_footer(items: list[tuple[str, str]]) -> Static:
        parts = [f"[bold]{key}[/]  {label}" for key, label in items if key]
        return Static("     ".join(parts), id="modal_hotkeys")


class LargeModalScreen(BaseModalScreen[ScreenResultT]):
    """Like :class:`BaseModalScreen` but sized 4/5 × 4/5 — meant for
    dialogs that carry lists, planners, or long confirmation details."""

    DEFAULT_CSS = """
    LargeModalScreen #modal_box {
        width: 80%;
        height: 80%;
        min-width: 80;
        min-height: 20;
    }
    """


__all__ = ["BaseModalScreen", "LargeModalScreen"]
