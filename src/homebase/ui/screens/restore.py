from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from ...commands.archive import normalize_restore_target
from ...core.constants import ACTION_ACCEPT, ACTION_CANCEL


class RestorePathScreen(ModalScreen[Path | None]):
    CSS = """
    Screen {
        align: center middle;
    }
    """
    BINDINGS = [
        ("enter", ACTION_ACCEPT, "Accept"),
        ("escape", ACTION_CANCEL, "Cancel"),
    ]

    def __init__(self, default_target: Path, base_dir_ref: Path) -> None:
        super().__init__()
        self.default_target = default_target
        self.base_dir_ref = base_dir_ref

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm_box"):
            yield Static("Restore to another location")
            yield Input(value=str(self.default_target), id="restore_input")
            yield Static("", id="restore_status")
            yield Static("enter=restore, esc=cancel")

    def on_mount(self) -> None:
        inp = self.query_one("#restore_input", Input)
        inp.focus()
        self._update_status(inp.value)

    def _resolve(self, raw: str) -> Path:
        text = raw.strip()
        if not text:
            return Path("")
        p = Path(text)
        if p.is_absolute():
            return p
        return self.base_dir_ref / p

    def _validate(self, raw: str) -> tuple[bool, str, Path | None]:
        if not raw.strip():
            return False, "target path is empty", None
        try:
            resolved = normalize_restore_target(
                self.base_dir_ref,
                self._resolve(raw),
                allow_outside_base=False,
            )
        except ValueError as exc:
            return False, str(exc), None
        if resolved.exists():
            return False, f"exists: {resolved}", resolved
        parent = resolved.parent
        if not parent.exists():
            return True, f"ok (parent will be created): {resolved}", resolved
        return True, f"ok: {resolved}", resolved

    def _update_status(self, raw: str) -> None:
        ok, msg, _resolved = self._validate(raw)
        if ok:
            self.query_one("#restore_status", Static).update(f"[green]{msg}[/]")
        else:
            self.query_one("#restore_status", Static).update(f"[red]{msg}[/]")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "restore_input":
            self._update_status(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "restore_input":
            return
        ok, _msg, resolved = self._validate(event.value)
        if ok and resolved is not None:
            self.dismiss(resolved)

    def action_accept(self) -> None:
        value = self.query_one("#restore_input", Input).value
        ok, _msg, resolved = self._validate(value)
        if ok and resolved is not None:
            self.dismiss(resolved)

    def action_cancel(self) -> None:
        self.dismiss(None)

