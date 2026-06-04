from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Static

from ...core.constants import ACTION_CANCEL
from .base import BaseModalScreen, LargeModalScreen


class ConfirmScreen(LargeModalScreen[bool]):
    CSS = """
    ConfirmScreen #modal_box { border: round $warning; }
    ConfirmScreen #confirm_details { height: 1fr; overflow-y: auto; }
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
        with Vertical(id="modal_box"):
            yield Static(f"[bold]{self.title}[/]")
            yield Static(self.details or "", id="confirm_details")
            yield self.hotkey_footer(
                [
                    ("y", "yes"),
                    ("n", "no"),
                    ("enter", "yes"),
                    ("space", "yes"),
                    ("esc", "no"),
                ]
            )

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


class ResultScreen(LargeModalScreen[None]):
    """Modal that summarises the outcome of an operation. Use this
    after a synchronous action so the user actually sees what
    happened (logs alone aren't visible unless the Events tab is
    open).
    """

    CSS = """
    ResultScreen #modal_box { border: round $success; }
    ResultScreen #result_context {
        color: $warning;
        margin: 1 0;
    }
    ResultScreen #result_details {
        height: 1fr;
        overflow-y: auto;
    }
    """
    BINDINGS = [
        ("enter", "close", "Close"),
        ("space", "close", "Close"),
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
    ]

    def __init__(
        self,
        title: str,
        summary: str,
        details: str,
        *,
        level: str = "info",
    ) -> None:
        super().__init__()
        self.title = title
        self.summary = summary
        self.details = details
        self.level = level if level in {"info", "warn", "error"} else "info"

    def compose(self) -> ComposeResult:
        title_color = {
            "info": "green",
            "warn": "yellow",
            "error": "red",
        }[self.level]
        with Vertical(id="modal_box"):
            yield Static(f"[bold {title_color}]{self.title}[/]")
            if self.summary:
                yield Static(self.summary, id="result_context")
            yield Static(self.details or "", id="result_details")
            yield self.hotkey_footer(
                [
                    ("enter", "close"),
                    ("space", "close"),
                    ("esc", "close"),
                    ("q", "close"),
                ]
            )

    def action_close(self) -> None:
        self.dismiss(None)


class RuntimeErrorScreen(BaseModalScreen[None]):
    CSS = """
    RuntimeErrorScreen #modal_box { border: round $error; }
    RuntimeErrorScreen #runtime_error_context {
        color: $warning;
        margin: 1 0;
    }
    RuntimeErrorScreen #runtime_error_details {
        height: 1fr;
        overflow-y: auto;
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
        with Vertical(id="modal_box"):
            yield Static(f"[bold red]{self.title}[/]")
            yield Static(
                f"[bold]Operation:[/] {self.context}", id="runtime_error_context"
            )
            yield Static(self.details, id="runtime_error_details", markup=False)
            yield self.hotkey_footer(
                [
                    ("enter", "close"),
                    ("space", "close"),
                    ("esc", "close"),
                    ("q", "close"),
                ]
            )

    def action_close(self) -> None:
        self.dismiss(None)


class InputScreen(BaseModalScreen[str | None]):
    CSS = """
    InputScreen #input_side_info {
        margin: 1 0 0 0;
        height: 1fr;
        overflow-y: auto;
    }
    """
    BINDINGS = [("escape", ACTION_CANCEL, "Cancel")]

    def __init__(
        self,
        title: str,
        placeholder: str,
        value: str = "",
        *,
        side_info: str | None = None,
    ) -> None:
        super().__init__()
        self.title = title
        self.placeholder = placeholder
        self.value = value
        self.side_info = side_info

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_box"):
            yield Static(self.title or "")
            yield Input(
                placeholder=self.placeholder, value=self.value, id="value_input"
            )
            if self.side_info is not None:
                yield Static(self.side_info, id="input_side_info")
            yield self.hotkey_footer(
                [
                    ("enter", "save"),
                    ("esc", "cancel"),
                ]
            )

    def on_mount(self) -> None:
        self.query_one("#value_input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_cancel(self) -> None:
        self.dismiss(None)


class ProcessWaitScreen(BaseModalScreen[None]):
    CSS = """
    ProcessWaitScreen #wait_details { height: 1fr; overflow-y: auto; }
    """

    def __init__(self, title: str, details: str) -> None:
        super().__init__()
        self.title = title
        self.details = details

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_box"):
            yield Static(f"[bold]{self.title}[/]")
            yield Static(self.details, id="wait_details")
            yield self.hotkey_footer(
                [("...", "waiting for process to finish")]
            )
