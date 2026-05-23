from __future__ import annotations

import difflib
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Static

from ...core.constants import (
    ACTION_ACCEPT,
    ACTION_CANCEL,
    COLLISION_RED_RAMP,
)
from .base import LargeModalScreen


def _similar_matches(
    base_dir: Path, query: str, limit: int = 5, *, exclude: str = "",
) -> list[tuple[str, int]]:
    q = query.strip().lower()
    if len(q) < 2:
        return []
    names: list[str] = []
    try:
        for p in base_dir.iterdir():
            if not p.is_dir():
                continue
            if p.name.startswith(".") or p.name.startswith("_"):
                continue
            if p.name == exclude:
                continue
            names.append(p.name)
    except OSError:
        return []
    scored: list[tuple[float, str]] = []
    for name in names:
        n = name.lower()
        ratio = difflib.SequenceMatcher(None, q, n).ratio()
        if q in n:
            ratio = max(ratio, 0.70)
        if n.startswith(q):
            ratio = max(ratio, 0.85)
        if n == q:
            ratio = 1.0
        if ratio >= 0.35:
            scored.append((ratio, name))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [(name, int(round(score * 100))) for score, name in scored[:limit]]


class RenameInputScreen(LargeModalScreen[str | None]):
    """Rename dialog with live preview of target path and collision
    matches. The result is the new bare name (same contract as
    :class:`InputScreen`); the caller handles the actual rename.
    """

    CSS = """
    RenameInputScreen #modal_box { border: round $primary; }
    RenameInputScreen #rename_preview {
        margin: 1 0 0 0;
        height: 1fr;
        overflow-y: auto;
    }
    """
    BINDINGS = [
        ("enter", ACTION_ACCEPT, "Accept"),
        ("escape", ACTION_CANCEL, "Cancel"),
    ]

    def __init__(
        self,
        title: str,
        current_path: Path,
        base_dir: Path,
        *,
        current_name: str | None = None,
    ) -> None:
        super().__init__()
        self.title_text = title
        self.current_path = current_path
        self.base_dir = base_dir
        self.current_name = current_name or current_path.name

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_box"):
            yield Static(self.title_text)
            yield Input(
                placeholder="new folder name",
                value=self.current_name,
                id="rename_input",
            )
            yield Static("", id="rename_preview")
            yield self.hotkey_footer(
                [
                    ("enter", "save"),
                    ("esc", "cancel"),
                ]
            )

    def on_mount(self) -> None:
        inp = self.query_one("#rename_input", Input)
        inp.focus()
        self._refresh(inp.value)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "rename_input":
            self._refresh(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "rename_input":
            self.dismiss(event.value.strip())

    def action_accept(self) -> None:
        value = self.query_one("#rename_input", Input).value.strip()
        self.dismiss(value)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _esc(self, text: object) -> str:
        return str(text).replace("[", "\\[").replace("]", "\\]")

    def _refresh(self, raw: str) -> None:
        name = raw.strip()
        widget = self.query_one("#rename_preview", Static)
        lines: list[str] = []
        if not name:
            lines.append("[dim](type a new name)[/]")
            widget.update("\n".join(lines))
            return
        if name == self.current_name:
            lines.append("[dim]unchanged[/]")
        else:
            target = self.current_path.with_name(name)
            try:
                target_rel = str(target.relative_to(self.base_dir))
            except ValueError:
                target_rel = str(target)
            if target.exists():
                lines.append(f"[red]target exists[/]: {self._esc(target_rel)}")
            else:
                lines.append(f"[green]target[/]: {self._esc(target_rel)}")
        suggestions = _similar_matches(
            self.base_dir, name, exclude=self.current_name,
        )
        if suggestions:
            lines.append("")
            lines.append("[bold]similar names in workspace[/]:")
            for item, pct in suggestions:
                bucket = max(
                    0, min(len(COLLISION_RED_RAMP) - 1, (100 - pct) // 10)
                )
                style = COLLISION_RED_RAMP[bucket]
                lines.append(f"  [{style}]- {self._esc(item)} ({pct}%)[/]")
        widget.update("\n".join(lines))
