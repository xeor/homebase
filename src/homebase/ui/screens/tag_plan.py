from __future__ import annotations

import difflib
from typing import Callable

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Static

from ...core.constants import (
    ACTION_ACCEPT,
    ACTION_CANCEL,
    COLOR_INFO_HEX,
    COLOR_SUCCESS_HEX,
)
from .basic import ConfirmScreen, InputScreen


class TagPlanScreen(ModalScreen[dict[str, str] | None]):
    CSS = """
    Screen {
        align: center middle;
    }
    """
    BINDINGS = [
        ("up", "move_up", "Up"),
        ("down", "move_down", "Down"),
        ("space", "cycle_plan", "Cycle plan"),
        ("ctrl+c", "clear_filter", "Clear filter"),
        ("ctrl+a", "add_tags", "Add tags"),
        ("ctrl+r", "rename_tag", "Rename tag"),
        ("ctrl+d", "delete_tag", "Delete tag"),
        ("enter", ACTION_ACCEPT, "Apply"),
        ("escape", ACTION_CANCEL, "Cancel"),
    ]

    def __init__(
        self,
        tags: list[str],
        presence: dict[str, str],
        other_counts: dict[str, int],
        mode: str = "full",
        on_rename_tag: Callable[[str, str], tuple[bool, str, bool]] | None = None,
        on_delete_tag: Callable[[str], tuple[bool, str]] | None = None,
        on_reload_model: Callable[
            [], tuple[list[str], dict[str, str], dict[str, int]]
        ]
        | None = None,
    ) -> None:
        super().__init__()
        self.tags = list(tags)
        self.presence = dict(presence)
        self.other_counts = dict(other_counts)
        self.mode = mode
        self.on_rename_tag = on_rename_tag
        self.on_delete_tag = on_delete_tag
        self.on_reload_model = on_reload_model
        self.index = 0
        self.plan = {tag: "keep" for tag in self.tags}
        self.filter_text = ""
        self.list_scroll_offset = 0
        self.status_text = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="tag_plan_box"):
            yield Static("Tag planner (multi-select safe)", id="choice_title")
            yield Static("", id="tag_filter", markup=False)
            yield Static("", id="tag_list")
            yield Static("", id="tag_help")
            yield Static("", id="tag_status")
            yield Static(
                "hotkeys: up/down move, space cycle, ctrl+c clear filter, ctrl+a add, ctrl+r rename, ctrl+d delete, enter apply, esc cancel",
                id="tag_hotkeys",
            )

    def on_mount(self) -> None:
        self._refresh_body()

    def _refresh_body(self) -> None:
        self.query_one("#tag_filter", Static).update(
            f"filter: {self.filter_text or '(all)'}"
        )
        list_lines: list[str] = []
        plan_mark = {"keep": "=", "add": "+", "remove": "-"}
        visible = self._visible_tags()
        if not visible:
            self.index = 0
            self.list_scroll_offset = 0
            if self.tags:
                list_lines.append("(no tags match current filter)")
            else:
                list_lines.append("(no tags available yet)")
                list_lines.append("press ctrl+a to add new tags")
            self.query_one("#tag_list", Static).update("\n".join(list_lines))
            self.query_one("#tag_help", Static).update(
                f"legend mark: [white]\\[=][/] keep [{COLOR_SUCCESS_HEX}]\\[+][/] set all [white]\\[-][/] remove all\n"
                f"legend color: [white]white[/]=none [{COLOR_INFO_HEX}]light blue[/]=mixed [{COLOR_SUCCESS_HEX}]light green[/]=all\n"
                "legend blank: [white]\\[ ][/] means keep + no existing tag\n"
                "cycle rules: white=[ ]<->+  blue=[=,+,-]  green=[=,-]\n"
                "others: non-selected projects using this tag"
            )
            self.query_one("#tag_status", Static).update(self.status_text)
            return

        if self.index >= len(visible):
            self.index = len(visible) - 1
        if self.index < 0:
            self.index = 0

        max_rows = 18
        try:
            measured = int(
                getattr(self.query_one("#tag_list", Static).size, "height", 0) or 0
            )
            if measured > 0:
                max_rows = max(6, measured)
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

        for i, tag in enumerate(window):
            absolute_i = self.list_scroll_offset + i
            cursor = ">" if absolute_i == self.index else " "
            plan = self.plan.get(tag, "keep")
            base_present = self.presence.get(tag, "none")

            color = "white"
            if base_present == "all":
                color = COLOR_SUCCESS_HEX
            elif base_present == "mixed":
                color = COLOR_INFO_HEX

            other = self.other_counts.get(tag, 0)
            mark = plan_mark.get(plan, "=")
            if plan == "keep" and base_present == "none":
                mark = " "
            list_lines.append(
                f"{cursor} [{color}]\\[{mark}][/] [{color}]{tag:<24}[/] others:{other:>4}"
            )
        if len(visible) > max_rows:
            start = self.list_scroll_offset + 1
            end = self.list_scroll_offset + len(window)
            list_lines.append(f"[dim]showing {start}-{end} of {len(visible)}[/]")
        self.query_one("#tag_list", Static).update("\n".join(list_lines))
        self.query_one("#tag_help", Static).update(
            f"legend mark: [white]\\[=][/] keep [{COLOR_SUCCESS_HEX}]\\[+][/] set all [white]\\[-][/] remove all\n"
            f"legend color: [white]white[/]=none [{COLOR_INFO_HEX}]light blue[/]=mixed [{COLOR_SUCCESS_HEX}]light green[/]=all\n"
            "legend blank: [white]\\[ ][/] means keep + no existing tag\n"
            "cycle rules: white=[ ]<->+  blue=[=,+,-]  green=[=,-]\n"
            "others: non-selected projects using this tag"
        )
        self.query_one("#tag_status", Static).update(self.status_text)

    def _visible_tags(self) -> list[str]:
        q = self.filter_text.strip().lower()
        if not q:
            return list(self.tags)

        ranked: list[tuple[float, str]] = []
        for tag in self.tags:
            t = tag.lower()
            score = 0.0
            if q in t:
                score = max(score, 0.80 + min(0.15, len(q) / max(1, len(t))))
            score = max(score, difflib.SequenceMatcher(None, q, t).ratio())

            qi = 0
            for ch in t:
                if qi < len(q) and ch == q[qi]:
                    qi += 1
            if qi == len(q):
                score = max(score, 0.72 + min(0.20, len(q) / max(1, len(t))))

            if score >= 0.45:
                ranked.append((score, tag))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [tag for _score, tag in ranked]

    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            self.filter_text = self.filter_text[:-1]
            self.index = 0
            self.list_scroll_offset = 0
            self._refresh_body()
            event.stop()
            return
        if len(event.key) == 1 and event.key.isprintable() and event.key != " ":
            self.filter_text += event.key
            self.index = 0
            self.list_scroll_offset = 0
            self._refresh_body()
            event.stop()
            return

    def action_clear_filter(self) -> None:
        if not self.filter_text:
            return
        self.filter_text = ""
        self._refresh_body()

    def action_move_up(self) -> None:
        visible = self._visible_tags()
        if not visible:
            return
        self.index = (self.index - 1) % len(visible)
        self._refresh_body()

    def action_move_down(self) -> None:
        visible = self._visible_tags()
        if not visible:
            return
        self.index = (self.index + 1) % len(visible)
        self._refresh_body()

    def action_cycle_plan(self) -> None:
        visible = self._visible_tags()
        if not visible:
            return
        tag = visible[self.index]
        cur = self.plan.get(tag, "keep")
        base_present = self.presence.get(tag, "none")
        if base_present == "none":
            allowed = ["keep", "add"]
        elif base_present == "all":
            allowed = ["keep", "remove"]
        else:
            allowed = ["keep", "add", "remove"]
        if cur not in allowed:
            cur = allowed[0]
        idx = allowed.index(cur)
        nxt = allowed[(idx + 1) % len(allowed)]
        self.plan[tag] = nxt
        self._refresh_body()

    def action_add_tags(self) -> None:
        self.app.push_screen(
            InputScreen("Add tags (comma separated)", "security, cli, ai"),
            self._on_add_tags,
        )

    def _set_status(self, text: str) -> None:
        self.status_text = text
        try:
            self.query_one("#tag_status", Static).update(text)
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

    def _reload_model(self) -> None:
        if self.on_reload_model is None:
            return
        try:
            tags, presence, other_counts = self.on_reload_model()
        except (
            LookupError,
            KeyError,
            IndexError,
            AttributeError,
            RuntimeError,
            ValueError,
            TypeError,
        ):
            return
        old_plan = dict(self.plan)
        self.tags = list(tags)
        self.presence = dict(presence)
        self.other_counts = dict(other_counts)
        self.plan = {tag: old_plan.get(tag, "keep") for tag in self.tags}
        self.index = 0
        self.list_scroll_offset = 0

    def action_rename_tag(self) -> None:
        if self.mode == "add_only" or self.on_rename_tag is None:
            self._set_status("[yellow]rename unavailable in this mode[/]")
            self._refresh_body()
            return
        visible = self._visible_tags()
        if not visible:
            return
        old = visible[self.index]
        self.app.push_screen(
            InputScreen("Rename tag", "new tag name", old),
            lambda value, old_tag=old: self._on_rename_tag_input(old_tag, value),
        )

    def _on_rename_tag_input(self, old_tag: str, value: str | None) -> None:
        if value is None:
            self._set_status("[dim]rename cancelled[/]")
            self._refresh_body()
            return
        new_tag = value.strip()
        if not new_tag:
            self._set_status("[yellow]rename aborted: empty tag[/]")
            self._refresh_body()
            return
        if new_tag == old_tag:
            self._set_status("[dim]rename skipped: unchanged[/]")
            self._refresh_body()
            return
        ok, msg, existed = self.on_rename_tag(old_tag, new_tag)
        if existed:
            self._set_status(f"[yellow]warning:[/] {msg}")
        else:
            self._set_status(f"[green]{msg}[/]" if ok else f"[red]{msg}[/]")
        self._reload_model()
        self._refresh_body()

    def action_delete_tag(self) -> None:
        if self.mode == "add_only" or self.on_delete_tag is None:
            self._set_status("[yellow]delete unavailable in this mode[/]")
            self._refresh_body()
            return
        visible = self._visible_tags()
        if not visible:
            return
        tag = visible[self.index]
        self.app.push_screen(
            ConfirmScreen(
                f"Delete tag '{tag}' from all projects?",
                "[cyan]effect[/]: removes this tag from active + archived project metadata\n"
                "[cyan]kept[/]: project folders/files are not modified",
            ),
            lambda ok, tag_name=tag: self._on_delete_tag_confirm(ok, tag_name),
        )

    def _on_delete_tag_confirm(self, ok: bool, tag: str) -> None:
        if not ok:
            self._set_status("[dim]delete cancelled[/]")
            self._refresh_body()
            return
        ok2, msg = self.on_delete_tag(tag)
        self._set_status(f"[green]{msg}[/]" if ok2 else f"[red]{msg}[/]")
        self._reload_model()
        self._refresh_body()

    def _on_add_tags(self, value: str | None) -> None:
        if not value:
            return
        incoming = [x.strip() for x in value.split(",") if x.strip()]
        for tag in incoming:
            if tag not in self.tags:
                self.tags.append(tag)
                self.presence[tag] = "none"
                self.plan[tag] = "add"
            else:
                self.plan[tag] = "add"
        self.tags = sorted(self.tags)
        visible = self._visible_tags()
        if visible:
            self.index = min(self.index, len(visible) - 1)
            self.list_scroll_offset = min(
                self.list_scroll_offset, max(0, len(visible) - 1)
            )
        self._refresh_body()

    def action_accept(self) -> None:
        self.dismiss(dict(self.plan))

    def action_cancel(self) -> None:
        self.dismiss(None)



