from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from ...core.constants import ACTION_ACCEPT, ACTION_CANCEL
from .base import LargeModalScreen


class MultiChoiceScreen(LargeModalScreen[set[str] | None]):
    CSS = """
    MultiChoiceScreen #choice_body { height: 1fr; overflow-y: auto; }
    """
    BINDINGS = [
        ("up", "move_up", "Up"),
        ("down", "move_down", "Down"),
        ("space", "toggle", "Toggle"),
        ("enter", ACTION_ACCEPT, "Accept"),
        ("escape", ACTION_CANCEL, "Cancel"),
    ]

    def __init__(
        self,
        title: str,
        options: list[tuple[str, str]],
        selected: set[str] | None = None,
    ) -> None:
        super().__init__()
        self.title = title
        self.options = options
        self.index = 0
        self.selected: set[str] = set(selected or set())

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_box"):
            yield Static(f"[bold]{self.title}[/]", id="choice_title")
            yield Static("", id="choice_body", markup=False)
            yield self.hotkey_footer(
                [
                    ("up/down", "move"),
                    ("space", "toggle"),
                    ("enter", "apply"),
                    ("esc", "cancel"),
                ]
            )

    def on_mount(self) -> None:
        self._refresh_body()

    def _refresh_body(self) -> None:
        lines = []
        for i, (key, label) in enumerate(self.options):
            prefix = ">" if i == self.index else " "
            mark = "[x]" if key in self.selected else "[ ]"
            lines.append(f"{prefix} {mark} {label}")
        self.query_one("#choice_body", Static).update("\n".join(lines))

    def action_move_up(self) -> None:
        if not self.options:
            return
        self.index = (self.index - 1) % len(self.options)
        self._refresh_body()

    def action_move_down(self) -> None:
        if not self.options:
            return
        self.index = (self.index + 1) % len(self.options)
        self._refresh_body()

    def action_toggle(self) -> None:
        if not self.options:
            return
        key = self.options[self.index][0]
        if key in self.selected:
            self.selected.remove(key)
        else:
            self.selected.add(key)
        self._refresh_body()

    def action_accept(self) -> None:
        self.dismiss(set(self.selected))

    def action_cancel(self) -> None:
        self.dismiss(None)
