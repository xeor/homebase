from __future__ import annotations

import difflib
import re
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key, Resize
from textual.widgets import Static, Tab, Tabs

from ...core.constants import ACTION_ACCEPT, ACTION_CANCEL
from .base import LargeModalScreen
from .listwin import compute_window, overflow_hint


class ActionPickerScreen(LargeModalScreen[str | None]):
    CSS = """
    ActionPickerScreen #action_picker_tabs { height: 3; margin: 0 0 1 0; }
    ActionPickerScreen #action_picker_body { height: 1fr; }
    """
    BINDINGS = [
        ("up", "move_up", "Up"),
        ("down", "move_down", "Down"),
        ("left", "prev_tab", "Prev tab"),
        ("right", "next_tab", "Next tab"),
        ("tab", "toggle_favorite", "Toggle favorite"),
        ("ctrl+@", "jump_tab_favorites", "Favorites tab"),
        ("ctrl+t", "jump_tab_target", "Target tab"),
        ("ctrl+g", "jump_tab_global", "Global tab"),
        ("ctrl+c", "clear_filter", "Clear filter"),
        ("enter", ACTION_ACCEPT, "Accept"),
        ("space", ACTION_ACCEPT, "Accept"),
        ("backspace", "backspace", "Backspace"),
        ("escape", ACTION_CANCEL, "Cancel"),
    ]

    def __init__(
        self,
        tabs: list[tuple[str, str, list[tuple[str, str]]]],
        *,
        default_tab: str | None = None,
        rebuild_tabs: Callable[
            [], list[tuple[str, str, list[tuple[str, str]]]]
        ] | None = None,
    ) -> None:
        super().__init__()
        self._rebuild_tabs = rebuild_tabs
        self._apply_tabs(tabs)
        # Favorites flagged for removal but not yet committed. The user
        # confirms by closing the dialog (esc/enter); pressing tab again
        # on a struck-through entry restores it. Scoped to the dialog
        # session — storage isn't touched until commit on dismiss.
        self._pending_remove: set[str] = set()
        if (
            default_tab
            and default_tab in self.actions_by_tab
            and not self._is_tab_disabled(default_tab)
        ):
            self.active_tab = default_tab
        else:
            self.active_tab = self._first_enabled_tab()
        self.filter_text = ""
        self.index = 0
        self.list_scroll_offset = 0

    def _apply_tabs(
        self, tabs: list[tuple[str, str, list[tuple[str, str]]]]
    ) -> None:
        self.tabs: list[tuple[str, str]] = [(key, label) for key, label, _ in tabs]
        self.actions_by_tab: dict[str, list[tuple[str, str]]] = {
            key: list(items) for key, _label, items in tabs
        }

    def _is_tab_disabled(self, key: str) -> bool:
        return not self.actions_by_tab.get(key, [])

    def _first_enabled_tab(self) -> str:
        for key, _label in self.tabs:
            if not self._is_tab_disabled(key):
                return key
        return self.tabs[0][0] if self.tabs else ""

    def _sync_tab_disabled_states(self) -> None:
        try:
            tabs_widget = self.query_one("#action_picker_tabs", Tabs)
        except LookupError:
            return
        for key, _label in self.tabs:
            try:
                tab = tabs_widget.query_one(f"Tab#{key}", Tab)
            except LookupError:
                continue
            tab.disabled = self._is_tab_disabled(key)

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_box"):
            yield Static("[bold]Actions[/]")
            yield Tabs(
                *[
                    Tab(label, id=key, disabled=self._is_tab_disabled(key))
                    for key, label in self.tabs
                ],
                id="action_picker_tabs",
            )
            yield Static("", id="action_picker_filter", markup=False)
            yield Static("", id="action_picker_body")
            yield self.hotkey_footer(
                [
                    ("type", "fuzzy filter"),
                    ("ctrl+c", "clear filter"),
                    ("up/down", "select"),
                    ("left/right", "tab"),
                    ("tab", "toggle favorite"),
                    ("enter", "select"),
                    ("esc", "cancel"),
                ]
            )

    def on_mount(self) -> None:
        self._sync_tab_disabled_states()
        self._refresh_body()

    def on_resize(self, _event: Resize) -> None:
        self._refresh_body()

    def on_tabs_tab_activated(self, event: Tabs.TabActivated) -> None:
        tabs_id = str(getattr(event.tabs, "id", "") or "")
        if tabs_id != "action_picker_tabs":
            return
        tab_id = str(getattr(getattr(event, "tab", None), "id", "") or "")
        keys = {k for k, _l in self.tabs}
        if tab_id in keys and not self._is_tab_disabled(tab_id):
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
        body = self.query_one("#action_picker_body", Static)
        lines: list[str] = []
        if not visible:
            self.index = 0
            self.list_scroll_offset = 0
            lines.append("(no actions match current filter)")
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
        for i, (key, label) in enumerate(window):
            absolute_i = offset + i
            cursor = ">" if absolute_i == self.index else " "
            if self.active_tab == "favorites" and key in self._pending_remove:
                label = f"[strike]{label}[/]"
            lines.append(f"{cursor} {label}")
        hint = overflow_hint(len(visible), offset, len(window))
        if hint is not None:
            lines.append(hint)
        body.update("\n".join(lines))
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

    def _cycle_tab(self, step: int) -> None:
        keys = [k for k, _l in self.tabs]
        if not keys:
            return
        enabled = [k for k in keys if not self._is_tab_disabled(k)]
        if not enabled:
            return
        if self.active_tab not in keys:
            self.active_tab = enabled[0]
        else:
            i = keys.index(self.active_tab)
            n = len(keys)
            for _ in range(n):
                i = (i + step) % n
                if not self._is_tab_disabled(keys[i]):
                    self.active_tab = keys[i]
                    break
        self.index = 0
        self.list_scroll_offset = 0
        self._refresh_body()

    def action_next_tab(self) -> None:
        self._cycle_tab(1)

    def action_prev_tab(self) -> None:
        self._cycle_tab(-1)

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
            self._commit_pending_removes()
            self.dismiss(None)
            return
        result = visible[self.index][0]
        self._commit_pending_removes()
        self.dismiss(result)

    def action_cancel(self) -> None:
        self._commit_pending_removes()
        self.dismiss(None)

    def _jump_to_tab(self, tab_id: str) -> None:
        if tab_id not in self.actions_by_tab or self._is_tab_disabled(tab_id):
            return
        self.active_tab = tab_id
        self.index = 0
        self.list_scroll_offset = 0
        self._refresh_body()

    def action_jump_tab_favorites(self) -> None:
        self._jump_to_tab("favorites")

    def action_jump_tab_target(self) -> None:
        self._jump_to_tab("target")

    def action_jump_tab_global(self) -> None:
        self._jump_to_tab("global")

    def action_toggle_favorite(self) -> None:
        visible = self._visible_actions()
        if not visible:
            return
        target = visible[self.index][0]
        if not target or target == "noop" or target.startswith("__hdr__"):
            return
        # In the Favorites tab, tab is a soft-delete with undo: the entry
        # is kept visible with a strikethrough until the dialog closes,
        # so an accidental keypress doesn't immediately destroy state.
        if self.active_tab == "favorites":
            if target in self._pending_remove:
                self._pending_remove.discard(target)
            else:
                self._pending_remove.add(target)
            self._refresh_body()
            return
        toggle = getattr(self.app, "_toggle_favorite_target", None)
        if not callable(toggle):
            return
        if not bool(toggle(target)):
            return
        if self._rebuild_tabs is not None:
            prev_index = self.index
            self._apply_tabs(self._rebuild_tabs())
            self._sync_tab_disabled_states()
            # Active tab is gone or became empty — jump to a usable tab
            # (Target preferred, else the first enabled).
            if (
                self.active_tab not in self.actions_by_tab
                or self._is_tab_disabled(self.active_tab)
            ):
                if not self._is_tab_disabled("target"):
                    self.active_tab = "target"
                else:
                    self.active_tab = self._first_enabled_tab()
                self.index = 0
                self.list_scroll_offset = 0
            else:
                # Keep the cursor on the same target if it's still visible,
                # otherwise stay near the previous row.
                visible_now = self._visible_actions()
                same_idx = next(
                    (i for i, (aid, _) in enumerate(visible_now) if aid == target),
                    -1,
                )
                if same_idx >= 0:
                    self.index = same_idx
                else:
                    self.index = min(prev_index, max(0, len(visible_now) - 1))
        self._refresh_body()

    def _commit_pending_removes(self) -> None:
        """Persist soft-deleted favorites to storage on dialog dismiss."""
        if not self._pending_remove:
            return
        toggle = getattr(self.app, "_toggle_favorite_target", None)
        if not callable(toggle):
            self._pending_remove.clear()
            return
        for target in list(self._pending_remove):
            toggle(target)
        self._pending_remove.clear()
