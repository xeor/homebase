from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static, TextArea

from ...core.constants import ACTION_ACCEPT, ACTION_CANCEL
from .base import LargeModalScreen


class MultilineInputScreen(LargeModalScreen[str | None]):
    CSS = """
    MultilineInputScreen #ml_input_body { height: 1fr; }
    MultilineInputScreen #ml_input_main { width: 80%; height: 1fr; }
    MultilineInputScreen #ml_input_side {
        width: 20%;
        height: 1fr;
        border: round $panel;
        padding: 0 1;
        margin: 0 0 0 1;
    }
    MultilineInputScreen #ml_input_title { height: 1; margin: 0 0 1 0; }
    MultilineInputScreen #ml_input_area { height: 1fr; }
    MultilineInputScreen #ml_input_side_body { height: 1fr; }
    """
    BINDINGS = [
        Binding("ctrl+s", ACTION_ACCEPT, "Save", priority=True),
        Binding("ctrl+enter", ACTION_ACCEPT, "Save", priority=True),
        Binding("ctrl+o", "open_note", "Open note", priority=True),
        Binding("escape", ACTION_CANCEL, "Cancel", priority=True),
    ]

    def __init__(
        self,
        title: str,
        placeholder: str = "",
        value: str = "",
        side_info: str = "",
        heading_level: int = 3,
    ) -> None:
        super().__init__()
        self.title_text = title
        self.placeholder_text = placeholder
        self.initial_value = value
        self.side_info = side_info
        self.heading_level = max(1, int(heading_level))

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_box"):
            yield Static(f"[bold]{self.title_text}[/]", id="ml_input_title")
            if self.placeholder_text:
                yield Static(f"[dim]{self.placeholder_text}[/]")
            with Horizontal(id="ml_input_body"):
                with Vertical(id="ml_input_main"):
                    yield TextArea(self.initial_value, id="ml_input_area")
                with Vertical(id="ml_input_side"):
                    yield Static("[bold]Log info[/]", id="ml_input_side_title")
                    yield Static("", id="ml_input_side_body")
            yield self.hotkey_footer(
                [
                    ("ctrl+s", "save"),
                    ("ctrl+o", "open note"),
                    ("esc", "cancel"),
                ]
            )

    def on_mount(self) -> None:
        self.query_one("#ml_input_area", TextArea).focus()
        self._refresh_side(self.initial_value)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self._refresh_side(event.text_area.text)

    def _refresh_side(self, text: str) -> None:
        warning = self._heading_warning(text)
        lines: list[str] = []
        if warning:
            lines.append(f"[bold red]warning[/]: {warning}")
            lines.append("")
        if self.side_info.strip():
            lines.append(self.side_info)
        self.query_one("#ml_input_side_body", Static).update("\n".join(lines))

    def _heading_warning(self, text: str) -> str:
        entry_level = self.heading_level
        max_level = min(6, self.heading_level + 1)
        for raw in str(text or "").splitlines():
            ls = raw.lstrip()
            if not ls.startswith("#"):
                continue
            level = 0
            for ch in ls:
                if ch == "#":
                    level += 1
                else:
                    break
            if level <= 0 or len(ls) <= level or ls[level] != " ":
                continue
            if level <= entry_level or level > max_level:
                return (
                    f"heading level {level} used (recommended: {entry_level + 1}..{max_level}; "
                    f"{entry_level} and lower can break log structure)"
                )
        return ""

    def action_accept(self) -> None:
        text = self.query_one("#ml_input_area", TextArea).text
        self.dismiss(text)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_open_note(self) -> None:
        app = self.app
        run_notes = getattr(app, "_run_notes_button_action", None)
        if callable(run_notes):
            run_notes("notes_create")
