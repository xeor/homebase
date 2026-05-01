from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from ...core.constants import ACTION_CANCEL


class ConfirmScreen(ModalScreen[bool]):
    CSS = """
    Screen {
        align: center middle;
    }
    #confirm_box {
        width: 110;
        height: 22;
        border: round $warning;
        background: $surface;
        padding: 1 2;
    }
    """
    BINDINGS = [
        ("y", "yes", "Yes"),
        ("n", "no", "No"),
        ("enter", "yes", "Yes"),
        ("space", "yes", "Yes"),
        ("escape", "no", "No"),
    ]

    def __init__(self, title: str, details: str = "") -> None:
        super().__init__()
        self.title = title
        self.details = details

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm_box"):
            yield Static(f"[bold]{self.title}[/]")
            if self.details:
                yield Static(self.details)
            yield Static(
                "[bold green]Y = Yes[/]  [bold red]N = No[/]  [dim](Enter/Space = Yes, Esc/N = No)[/]"
            )

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)

class RuntimeErrorScreen(ModalScreen[None]):
    CSS = """
    Screen {
        align: center middle;
    }
    #runtime_error_box {
        width: 112;
        height: 28;
        border: round $error;
        background: $surface;
        padding: 1 2;
    }
    #runtime_error_context {
        color: $warning;
        margin: 1 0;
    }
    #runtime_error_details {
        height: 1fr;
    }
    """
    BINDINGS = [
        ("enter", "close", "Close"),
        ("space", "close", "Close"),
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
    ]

    def __init__(self, title: str, context: str, details: str) -> None:
        super().__init__()
        self.title = title
        self.context = context
        self.details = details

    def compose(self) -> ComposeResult:
        with Vertical(id="runtime_error_box"):
            yield Static(f"[bold red]{self.title}[/]")
            yield Static(
                f"[bold]Operation:[/] {self.context}", id="runtime_error_context"
            )
            yield Static(self.details, id="runtime_error_details", markup=False)
            yield Static("[dim]enter/space/esc/q = close[/]")

    def action_close(self) -> None:
        self.dismiss(None)

class InputScreen(ModalScreen[str | None]):
    CSS = """
    Screen {
        align: center middle;
    }
    """
    BINDINGS = [("escape", ACTION_CANCEL, "Cancel")]

    def __init__(self, title: str, placeholder: str, value: str = "") -> None:
        super().__init__()
        self.title = title
        self.placeholder = placeholder
        self.value = value

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm_box"):
            yield Static(self.title)
            yield Input(
                placeholder=self.placeholder, value=self.value, id="value_input"
            )
            yield Static("enter=save, esc=cancel")

    def on_mount(self) -> None:
        self.query_one("#value_input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_cancel(self) -> None:
        self.dismiss(None)

