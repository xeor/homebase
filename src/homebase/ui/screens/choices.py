from __future__ import annotations

import difflib
import re

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key, Resize
from textual.widgets import Static

from ...core.constants import ACTION_ACCEPT, ACTION_CANCEL
from .base import LargeModalScreen
from .listwin import compute_window, overflow_hint


class SingleChoiceScreen(LargeModalScreen[str | None]):
    CSS = """
    SingleChoiceScreen #choice_body { height: 1fr; }
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
    ) -> None:
        super().__init__()
        self.title = title
        self.options = options
        self.index = 0
        self.list_scroll_offset = 0
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
        with Vertical(id="modal_box"):
            yield Static(f"[bold]{self.title}[/]", id="choice_title")
            yield Static("", id="choice_body", markup=False)
            yield self.hotkey_footer(
                [
                    ("up/down", "move"),
                    ("enter", "select"),
                    ("space", "select"),
                    ("esc", "cancel"),
                ]
            )

    def on_mount(self) -> None:
        self._refresh_body()

    def on_resize(self, _event: Resize) -> None:
        self._refresh_body()

    def _refresh_body(self) -> None:
        body = self.query_one("#choice_body", Static)
        offset, max_rows = compute_window(
            total=len(self.options),
            cursor=self.index,
            current_offset=self.list_scroll_offset,
            body_widget=body,
            reserve_bottom_rows=1,
        )
        self.list_scroll_offset = offset
        window = self.options[offset : offset + max_rows]
        lines: list[str] = []
        for i, (_k, label) in enumerate(window):
            absolute = offset + i
            if self._is_header(absolute):
                lines.append(f"  {label}")
                continue
            prefix = ">" if absolute == self.index else " "
            lines.append(f"{prefix} {label}")
        hint = overflow_hint(len(self.options), offset, len(window))
        if hint is not None:
            lines.append(hint)
        body.update("\n".join(lines))

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


class FuzzyChoiceScreen(LargeModalScreen[str | None]):
    CSS = """
    FuzzyChoiceScreen #choice_picker_body { height: 1fr; }
    """
    BINDINGS = [
        ("up", "move_up", "Up"),
        ("down", "move_down", "Down"),
        ("ctrl+c", "clear_filter", "Clear filter"),
        ("enter", ACTION_ACCEPT, "Accept"),
        ("space", ACTION_ACCEPT, "Accept"),
        ("backspace", "backspace", "Backspace"),
        ("escape", ACTION_CANCEL, "Cancel"),
    ]

    def __init__(self, title: str, options: list[tuple[str, str]]) -> None:
        super().__init__()
        self.title = title
        self.options = options
        self.filter_text = ""
        self.index = 0
        self.list_scroll_offset = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_box"):
            yield Static(f"[bold]{self.title}[/]")
            yield Static("", id="choice_picker_filter", markup=False)
            yield Static("", id="choice_picker_body")
            yield self.hotkey_footer(
                [
                    ("type", "fuzzy filter"),
                    ("ctrl+c", "clear filter"),
                    ("up/down", "select"),
                    ("enter", "accept"),
                    ("esc", "cancel"),
                ]
            )

    def on_mount(self) -> None:
        self._refresh_body()

    def on_resize(self, _event: Resize) -> None:
        self._refresh_body()

    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            self.action_backspace()
            event.stop()
            return
        if event.character is not None and event.character.isprintable():
            self.filter_text += event.character
            self.index = 0
            self.list_scroll_offset = 0
            self._refresh_body()
            event.stop()

    def _search_text(self, item: tuple[str, str]) -> str:
        key, label = item
        label = re.sub(r"\[[^\]]*\]", "", label)
        return f"{key} {label}".lower()

    def _visible_options(self) -> list[tuple[str, str]]:
        q = self.filter_text.strip().lower()
        if not q:
            return self.options
        ranked: list[tuple[float, tuple[str, str]]] = []
        for item in self.options:
            text = self._search_text(item)
            score = 0.0
            if q in text:
                score = max(score, 0.80 + min(0.15, len(q) / max(1, len(text))))
            score = max(score, difflib.SequenceMatcher(None, q, text).ratio())
            qi = 0
            for ch in text:
                if qi < len(q) and ch == q[qi]:
                    qi += 1
            if qi == len(q):
                score = max(score, 0.72 + min(0.20, len(q) / max(1, len(text))))
            if score >= 0.45:
                ranked.append((score, item))
        ranked.sort(key=lambda pair: (-pair[0], pair[1][1]))
        return [item for _score, item in ranked]

    def _refresh_body(self) -> None:
        self.query_one("#choice_picker_filter", Static).update(
            f"filter: {self.filter_text or '(all)'}"
        )
        visible = self._visible_options()
        body = self.query_one("#choice_picker_body", Static)
        lines: list[str] = []
        if not visible:
            self.index = 0
            self.list_scroll_offset = 0
            lines.append("(no files match current filter)")
            body.update("\n".join(lines))
            return
        offset, max_rows = compute_window(
            total=len(visible),
            cursor=self.index,
            current_offset=self.list_scroll_offset,
            body_widget=body,
            reserve_bottom_rows=1,
        )
        self.list_scroll_offset = offset
        self.index = min(max(self.index, 0), len(visible) - 1)
        window = visible[offset : offset + max_rows]
        for i, (_key, label) in enumerate(window):
            absolute_i = offset + i
            cursor = ">" if absolute_i == self.index else " "
            lines.append(f"{cursor} {label}")
        hint = overflow_hint(len(visible), offset, len(window))
        if hint is not None:
            lines.append(hint)
        body.update("\n".join(lines))

    def action_move_up(self) -> None:
        visible = self._visible_options()
        if not visible:
            return
        self.index = (self.index - 1) % len(visible)
        self._refresh_body()

    def action_move_down(self) -> None:
        visible = self._visible_options()
        if not visible:
            return
        self.index = (self.index + 1) % len(visible)
        self._refresh_body()

    def action_backspace(self) -> None:
        if not self.filter_text:
            return
        self.filter_text = self.filter_text[:-1]
        self.index = 0
        self.list_scroll_offset = 0
        self._refresh_body()

    def action_clear_filter(self) -> None:
        if not self.filter_text:
            return
        self.filter_text = ""
        self._refresh_body()

    def action_accept(self) -> None:
        visible = self._visible_options()
        if not visible:
            self.dismiss(None)
            return
        self.dismiss(visible[self.index][0])

    def action_cancel(self) -> None:
        self.dismiss(None)
