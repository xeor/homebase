from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from ...core.constants import ACTION_ACCEPT, ACTION_CANCEL


class SingleChoiceScreen(ModalScreen[str | None]):
    CSS = """
    Screen {
        align: center middle;
    }
    """
    BINDINGS = [
        ("up", "move_up", "Up"),
        ("down", "move_down", "Down"),
        ("enter", ACTION_ACCEPT, "Accept"),
        ("space", ACTION_ACCEPT, "Accept"),
        ("escape", ACTION_CANCEL, "Cancel"),
    ]

    def __init__(
        self,
        title: str,
        options: list[tuple[str, str]],
        box_width: int = 70,
        box_height: int = 16,
    ) -> None:
        super().__init__()
        self.title = title
        self.options = options
        self.index = 0
        self.box_width = box_width
        self.box_height = box_height
        self._ensure_valid_index()

    def _is_header(self, idx: int) -> bool:
        if idx < 0 or idx >= len(self.options):
            return True
        key = self.options[idx][0]
        return key.startswith("__hdr__")

    def _ensure_valid_index(self) -> None:
        if not self.options:
            self.index = 0
            return
        if (
            self.index < 0
            or self.index >= len(self.options)
            or self._is_header(self.index)
        ):
            for i, (k, _label) in enumerate(self.options):
                if not k.startswith("__hdr__"):
                    self.index = i
                    return
            self.index = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm_box"):
            yield Static(f"[bold]{self.title}[/]", id="choice_title")
            yield Static("", id="choice_body", markup=False)
            yield Static(
                "[dim]up/down to move, enter/space to select, esc to cancel[/]"
            )

    def on_mount(self) -> None:
        box = self.query_one("#confirm_box", Vertical)
        box.styles.width = self.box_width
        box.styles.height = self.box_height
        self._refresh_body()

    def _refresh_body(self) -> None:
        lines = []
        for i, (_k, label) in enumerate(self.options):
            if self._is_header(i):
                lines.append(f"  {label}")
                continue
            prefix = ">" if i == self.index else " "
            lines.append(f"{prefix} {label}")
        self.query_one("#choice_body", Static).update("\n".join(lines))

    def action_move_up(self) -> None:
        if not self.options:
            return
        for _ in range(len(self.options)):
            self.index = (self.index - 1) % len(self.options)
            if not self._is_header(self.index):
                break
        self._refresh_body()

    def action_move_down(self) -> None:
        if not self.options:
            return
        for _ in range(len(self.options)):
            self.index = (self.index + 1) % len(self.options)
            if not self._is_header(self.index):
                break
        self._refresh_body()

    def action_accept(self) -> None:
        if not self.options:
            self.dismiss(None)
            return
        if self._is_header(self.index):
            return
        self.dismiss(self.options[self.index][0])

    def action_cancel(self) -> None:
        self.dismiss(None)

