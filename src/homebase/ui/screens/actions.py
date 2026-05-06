from __future__ import annotations

import difflib
import re

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Static, Tab, Tabs

from ...core.constants import ACTION_ACCEPT, ACTION_CANCEL


class ActionPickerScreen(ModalScreen[str | None]):
    CSS = """
    Screen {
        align: center middle;
    }
    #action_picker_box {
        width: 100;
        height: 26;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    #action_picker_tabs { height: 3; margin: 0 0 1 0; }
    #action_picker_spacer { height: 1fr; }
    """
    BINDINGS = [
        ("up", "move_up", "Up"),
        ("down", "move_down", "Down"),
        ("left", "prev_tab", "Prev tab"),
        ("right", "next_tab", "Next tab"),
        ("tab", "next_tab", "Next tab"),
        ("backtab", "prev_tab", "Prev tab"),
        ("ctrl+c", "clear_filter", "Clear filter"),
        ("enter", ACTION_ACCEPT, "Accept"),
        ("space", ACTION_ACCEPT, "Accept"),
        ("backspace", "backspace", "Backspace"),
        ("escape", ACTION_CANCEL, "Cancel"),
    ]

    def __init__(
        self,
        button_actions: list[tuple[str, str]],
        target_actions: list[tuple[str, str]],
        global_actions: list[tuple[str, str]],
    ) -> None:
        super().__init__()
        self.tabs: list[tuple[str, str]] = []
        if button_actions:
            self.tabs.append(("buttons", "Buttons"))
        self.tabs.extend(
            [
                ("target", "Target"),
                ("global", "Global"),
            ]
        )
        self.actions_by_tab: dict[str, list[tuple[str, str]]] = {
            "buttons": button_actions,
            "target": target_actions,
            "global": global_actions,
        }
        self.active_tab = "buttons" if button_actions else "target"
        self.filter_text = ""
        self.index = 0
        self.list_scroll_offset = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="action_picker_box"):
            yield Static("[bold]Actions[/]")
            yield Tabs(
                *[Tab(label, id=key) for key, label in self.tabs],
                id="action_picker_tabs",
            )
            yield Static("", id="action_picker_filter", markup=False)
            yield Static("", id="action_picker_body")
            yield Static("", id="action_picker_spacer")
            yield Static(
                "type fuzzy filter, ctrl+c clear filter, up/down select, left/right tab, enter select, esc cancel"
            )

    def on_mount(self) -> None:
        self._refresh_body()

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tabs_id = str(getattr(event.tabs, "id", "") or "")
        if tabs_id != "action_picker_tabs":
            return
        tab_id = str(getattr(getattr(event, "tab", None), "id", "") or "")
        keys = {k for k, _l in self.tabs}
        if tab_id in keys:
            self.active_tab = tab_id
            self.index = 0
            self.list_scroll_offset = 0
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

    def _actions_in_tab(self) -> list[tuple[str, str]]:
        return list(self.actions_by_tab.get(self.active_tab, []))

    def _search_text(self, item: tuple[str, str]) -> str:
        key, label = item
        label = re.sub(r"\[[^\]]*\]", "", label)
        return f"{key} {label}".lower()

    def _visible_actions(self) -> list[tuple[str, str]]:
        actions = self._actions_in_tab()
        q = self.filter_text.strip().lower()
        if not q:
            return actions
        ranked: list[tuple[float, tuple[str, str]]] = []
        for item in actions:
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
        self.query_one("#action_picker_filter", Static).update(
            f"tab: {self.active_tab}  filter: {self.filter_text or '(all)'}"
        )
        visible = self._visible_actions()
        lines: list[str] = []
        if not visible:
            self.index = 0
            self.list_scroll_offset = 0
            lines.append("(no actions match current filter)")
            self.query_one("#action_picker_body", Static).update("\n".join(lines))
            return

        if self.index >= len(visible):
            self.index = len(visible) - 1
        if self.index < 0:
            self.index = 0

        max_rows = 14
        max_offset = max(0, len(visible) - max_rows)
        if self.list_scroll_offset > max_offset:
            self.list_scroll_offset = max_offset
        if self.index < self.list_scroll_offset:
            self.list_scroll_offset = self.index
        elif self.index >= self.list_scroll_offset + max_rows:
            self.list_scroll_offset = self.index - max_rows + 1

        window = visible[
            self.list_scroll_offset : self.list_scroll_offset + max_rows
        ]
        for i, (_key, label) in enumerate(window):
            absolute_i = self.list_scroll_offset + i
            cursor = ">" if absolute_i == self.index else " "
            lines.append(f"{cursor} {label}")
        if len(visible) > max_rows:
            start = self.list_scroll_offset + 1
            end = self.list_scroll_offset + len(window)
            lines.append(f"[dim]showing {start}-{end} of {len(visible)}[/]")
        self.query_one("#action_picker_body", Static).update("\n".join(lines))
        tabs = self.query_one("#action_picker_tabs", Tabs)
        try:
            tabs.active = self.active_tab
        except (
            LookupError,
            KeyError,
            IndexError,
            AttributeError,
            RuntimeError,
            ValueError,
            TypeError,
        ):
            pass

    def action_move_up(self) -> None:
        visible = self._visible_actions()
        if not visible:
            return
        self.index = (self.index - 1) % len(visible)
        self._refresh_body()

    def action_move_down(self) -> None:
        visible = self._visible_actions()
        if not visible:
            return
        self.index = (self.index + 1) % len(visible)
        self._refresh_body()

    def action_next_tab(self) -> None:
        keys = [k for k, _l in self.tabs]
        if self.active_tab not in keys:
            self.active_tab = keys[0]
        else:
            i = keys.index(self.active_tab)
            self.active_tab = keys[(i + 1) % len(keys)]
        self.index = 0
        self.list_scroll_offset = 0
        self._refresh_body()

    def action_prev_tab(self) -> None:
        keys = [k for k, _l in self.tabs]
        if self.active_tab not in keys:
            self.active_tab = keys[0]
        else:
            i = keys.index(self.active_tab)
            self.active_tab = keys[(i - 1) % len(keys)]
        self.index = 0
        self.list_scroll_offset = 0
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
        visible = self._visible_actions()
        if not visible:
            self.dismiss(None)
            return
        self.dismiss(visible[self.index][0])

    def action_cancel(self) -> None:
        self.dismiss(None)
