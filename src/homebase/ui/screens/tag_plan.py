from __future__ import annotations

from pathlib import Path
from typing import Callable

from rich.markup import escape as rich_escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Static

from ...config.tag_rules import resolve_for_display
from ...core.constants import (
    ACTION_ACCEPT,
    ACTION_CANCEL,
    COLOR_INFO_HEX,
    COLOR_SUCCESS_HEX,
)
from . import tag_tree as tag_tree_view
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
        *,
        base_dir: Path | None = None,
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
        self.base_dir = base_dir
        self.on_rename_tag = on_rename_tag
        self.on_delete_tag = on_delete_tag
        self.on_reload_model = on_reload_model
        self.plan = {tag: "keep" for tag in self.tags}
        self.filter_text = ""
        self.status_text = ""
        self.index = 0
        self._tree: tag_tree_view.TagTreeView | None = None
        self._rebuild_tree()
        self._cached_rows: list[tag_tree_view.TreeRow] = []
        self._cached_rows_token: tuple[str, int] | None = None
        self._snap_cursor_to_selectable()

    # ---- tree maintenance -----------------------------------------

    def _rebuild_tree(self) -> None:
        if self.base_dir is None:
            self._tree = None
            return
        self._tree = tag_tree_view.build_tag_tree(self.tags, self.base_dir)

    def _visible_rows(self) -> list[tag_tree_view.TreeRow]:
        # Cache by (filter text, tag-list size) so repeated calls in
        # one paint cycle don't re-walk the tree.
        token = (self.filter_text, len(self.tags))
        if self._cached_rows_token == token and self._cached_rows:
            return self._cached_rows
        rows = self._build_rows()
        self._cached_rows = rows
        self._cached_rows_token = token
        return rows

    def _build_rows(self) -> list[tag_tree_view.TreeRow]:
        if self._tree is None:
            # Defensive: no base_dir, fall back to a flat unfiltered
            # view of the explicit tag list.
            q = self.filter_text.strip().lower()
            return [
                tag_tree_view.TreeRow(
                    name=tag,
                    depth=0,
                    parent_path=(),
                    group_only=False,
                    matched=bool(q) and q in tag.lower(),
                )
                for tag in self.tags
                if not q or q in tag.lower()
            ]
        visible, matched = tag_tree_view.filter_visible(
            self._tree, self.filter_text, self.base_dir,
        )
        return tag_tree_view.flatten_for_render(self._tree, visible, matched)

    def _invalidate_rows_cache(self) -> None:
        self._cached_rows = []
        self._cached_rows_token = None

    def _snap_cursor_to_selectable(self) -> None:
        rows = self._visible_rows()
        if not rows:
            self.index = 0
            return
        if 0 <= self.index < len(rows) and not rows[self.index].group_only:
            return
        first = tag_tree_view.first_selectable_index(rows)
        if first >= 0:
            self.index = first
        else:
            self.index = 0

    def _jump_to_first_match(self) -> None:
        """After a filter change, park the cursor on the first
        matched selectable row so the user can hit space straight
        away. When the match is purely a group-only ancestor (i.e.
        the user typed the name of a group), fall back to the first
        selectable child so they can still drill in."""
        self._invalidate_rows_cache()
        rows = self._visible_rows()
        if not rows:
            self.index = 0
            return
        matched = tag_tree_view.first_matched_selectable_index(rows)
        if matched >= 0:
            self.index = matched
            return
        first = tag_tree_view.first_selectable_index(rows)
        self.index = first if first >= 0 else 0

    def _current_row(self) -> tag_tree_view.TreeRow | None:
        rows = self._visible_rows()
        if not rows or self.index < 0 or self.index >= len(rows):
            return None
        return rows[self.index]

    # ---- composition / render -------------------------------------

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

    def _legend_text(self) -> str:
        return (
            f"legend mark: [white]\\[=][/] keep "
            f"[{COLOR_SUCCESS_HEX}]\\[+][/] set all "
            f"[white]\\[-][/] remove all  "
            f"[dim]\\[·][/] group-only (read-only)\n"
            f"legend color: [white]white[/]=none "
            f"[{COLOR_INFO_HEX}]light blue[/]=mixed "
            f"[{COLOR_SUCCESS_HEX}]light green[/]=all\n"
            "legend blank: [white]\\[ ][/] means keep + no existing tag\n"
            "cycle rules: white=[ ]<->+  blue=[=,+,-]  green=[=,-]\n"
            "others: non-selected projects using this tag"
        )

    def _format_row(self, row: tag_tree_view.TreeRow, is_cursor: bool) -> str:
        plan_mark = {"keep": "=", "add": "+", "remove": "-"}
        indent = "  " * row.depth
        cursor = ">" if is_cursor else " "
        tag = row.name
        # Group-only rows are headers — non-selectable, dimmed, with
        # the explicit ``(group-only)`` label. Even here we still
        # render the configured display string so a styled emoji
        # prefix (e.g. ``⚡ priority``) shows through; the bracket
        # checkbox stays the distinct part for the rest of the rows.
        if row.group_only:
            display = self._resolve_display(tag)
            return (
                f"{cursor} {indent}[dim]\\[·] "
                f"{rich_escape(display)}  (group-only)[/]"
            )
        plan = self.plan.get(tag, "keep")
        base_present = self.presence.get(tag, "none")
        # The checkbox color reflects presence across selected
        # projects — that's the distinct cue the user reads for
        # picking. Tag NAMES use their configured style so colour
        # + bold + prefix/suffix all come through.
        if base_present == "all":
            marker_color = COLOR_SUCCESS_HEX
        elif base_present == "mixed":
            marker_color = COLOR_INFO_HEX
        else:
            marker_color = "white"
        mark = plan_mark.get(plan, "=")
        if plan == "keep" and base_present == "none":
            mark = " "
        display, style_spec = self._resolve_display_and_style(tag)
        other = self.other_counts.get(tag, 0)
        match_glyph = " *" if row.matched else "  "
        return (
            f"{cursor} {indent}"
            f"[{marker_color}]\\[{mark}][/] "
            f"[{style_spec}]{rich_escape(display)}[/]"
            f"{match_glyph}  "
            f"[dim]others:{other}[/]"
        )

    def _resolve_display_and_style(self, tag: str) -> tuple[str, str]:
        if self.base_dir is None:
            return tag, "white"
        try:
            resolved = resolve_for_display(tag, self.base_dir)
        except (OSError, ValueError):
            return tag, "white"
        return resolved.display, resolved.style_spec

    def _resolve_display(self, tag: str) -> str:
        return self._resolve_display_and_style(tag)[0]

    def _refresh_body(self) -> None:
        self._invalidate_rows_cache()
        self.query_one("#tag_filter", Static).update(
            f"filter: {self.filter_text or '(all)'}"
        )
        rows = self._visible_rows()
        if not rows:
            if self.tags:
                lines = ["(no tags match current filter)"]
            else:
                lines = [
                    "(no tags available yet)",
                    "press ctrl+a to add new tags",
                ]
            self.query_one("#tag_list", Static).update("\n".join(lines))
            self.query_one("#tag_help", Static).update(self._legend_text())
            self.query_one("#tag_status", Static).update(self.status_text)
            return

        self._snap_cursor_to_selectable()

        # Render every row at once. The previous implementation
        # windowed by the measured widget height and fell back to a
        # fixed 18-row cap when the widget hadn't been sized yet —
        # that's the "only 20 visible on first paint" bug. Letting
        # the Static hold the full list defers any clipping decision
        # to Textual's layout, which already knows how much room the
        # modal actually has.
        lines = [
            self._format_row(row, is_cursor=idx == self.index)
            for idx, row in enumerate(rows)
        ]
        self.query_one("#tag_list", Static).update("\n".join(lines))
        self.query_one("#tag_help", Static).update(self._legend_text())
        self.query_one("#tag_status", Static).update(self.status_text)

    # ---- keyboard / navigation ------------------------------------

    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            self.filter_text = self.filter_text[:-1]
            self._jump_to_first_match()
            self._refresh_body()
            event.stop()
            return
        if len(event.key) == 1 and event.key.isprintable() and event.key != " ":
            self.filter_text += event.key
            self._jump_to_first_match()
            self._refresh_body()
            event.stop()
            return

    def action_clear_filter(self) -> None:
        if not self.filter_text:
            return
        self.filter_text = ""
        self._jump_to_first_match()
        self._refresh_body()

    def action_move_up(self) -> None:
        rows = self._visible_rows()
        if not rows or tag_tree_view.first_selectable_index(rows) < 0:
            return
        self.index = tag_tree_view.next_selectable_index(
            rows, self.index, forward=False,
        )
        self._refresh_body()

    def action_move_down(self) -> None:
        rows = self._visible_rows()
        if not rows or tag_tree_view.first_selectable_index(rows) < 0:
            return
        self.index = tag_tree_view.next_selectable_index(
            rows, self.index, forward=True,
        )
        self._refresh_body()

    def action_cycle_plan(self) -> None:
        row = self._current_row()
        if row is None or row.group_only:
            return
        tag = row.name
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

    # ---- add / rename / delete ------------------------------------

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
        self._rebuild_tree()
        self._invalidate_rows_cache()
        self._snap_cursor_to_selectable()

    def action_rename_tag(self) -> None:
        if self.mode == "add_only" or self.on_rename_tag is None:
            self._set_status("[yellow]rename unavailable in this mode[/]")
            self._refresh_body()
            return
        row = self._current_row()
        if row is None or row.group_only:
            return
        old = row.name
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
        row = self._current_row()
        if row is None or row.group_only:
            return
        tag = row.name
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
        self.tags = sorted(self.tags)
        self._rebuild_tree()
        self._invalidate_rows_cache()
        self._snap_cursor_to_selectable()
        self._refresh_body()

    # ---- accept / cancel ------------------------------------------

    def action_accept(self) -> None:
        # Group-only tags can never end up as anything but ``keep``
        # because the toggle action refuses to touch them. Strip them
        # from the returned plan defensively so callers don't have to
        # filter again.
        clean = {
            tag: state for tag, state in self.plan.items()
            if not (
                self._tree is not None
                and tag in self._tree.group_only
            )
        }
        self.dismiss(clean)

    def action_cancel(self) -> None:
        self.dismiss(None)
