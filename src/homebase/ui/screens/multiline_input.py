from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, TextArea

from ...core.constants import ACTION_ACCEPT, ACTION_CANCEL


class MultilineInputScreen(ModalScreen[str | None]):
    CSS = """
    Screen {
        align: center middle;
    }
    #ml_input_box {
        width: 90%;
        height: 70%;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    #ml_input_title { height: 1; margin: 0 0 1 0; }
    #ml_input_help { height: 1; color: $text-muted; margin: 1 0 0 0; }
    #ml_input_area { height: 1fr; }
    """
    BINDINGS = [
        Binding("ctrl+s", ACTION_ACCEPT, "Save", priority=True),
        Binding("ctrl+enter", ACTION_ACCEPT, "Save", priority=True),
        Binding("escape", ACTION_CANCEL, "Cancel", priority=True),
    ]

    def __init__(self, title: str, placeholder: str = "", value: str = "") -> None:
        super().__init__()
        self.title_text = title
        self.placeholder_text = placeholder
        self.initial_value = value

    def compose(self) -> ComposeResult:
        with Vertical(id="ml_input_box"):
            yield Static(f"[bold]{self.title_text}[/]", id="ml_input_title")
            if self.placeholder_text:
                yield Static(f"[dim]{self.placeholder_text}[/]")
            yield TextArea(self.initial_value, id="ml_input_area")
            yield Static(
                "ctrl+s = save, esc = cancel",
                id="ml_input_help",
            )

    def on_mount(self) -> None:
        self.query_one("#ml_input_area", TextArea).focus()

    def action_accept(self) -> None:
        text = self.query_one("#ml_input_area", TextArea).text
        self.dismiss(text)

    def action_cancel(self) -> None:
        self.dismiss(None)
