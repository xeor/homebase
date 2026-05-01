from __future__ import annotations

import difflib

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Static

from ...core.constants import ACTION_ACCEPT, ACTION_CANCEL, COLOR_ACCENT_HEX
from ...core.models import PaneRef


class PaneChoiceScreen(ModalScreen[str | None]):
    CSS = """
    Screen {
        align: center middle;
    }
    #pane_choice_box {
        width: 140;
        height: 30;
        border: round $accent;
        background: $surface;
        padding: 1 2;
    }
    #pane_filter { color: $text-muted; height: 1; }
    #pane_choice_body { height: 1fr; }
    #pane_choice_hint { color: $text-muted; height: 1; }
    """
    BINDINGS = [
        ("up", "move_up", "Up"),
        ("down", "move_down", "Down"),
        ("left", "move_left", "Left"),
        ("right", "move_right", "Right"),
        ("tab", "move_right", "Next pane"),
        ("shift+tab", "move_left", "Prev pane"),
        ("backtab", "move_left", "Prev pane"),
        ("ctrl+c", "clear_filter", "Clear filter"),
        ("enter", ACTION_ACCEPT, "Accept"),
        ("space", ACTION_ACCEPT, "Accept"),
        ("escape", ACTION_CANCEL, "Cancel"),
    ]

    def __init__(self, title: str, panes: list[PaneRef]) -> None:
        super().__init__()
        self.title = title
        self.panes = list(panes)
        self.row_index = 0
        self.col_index = 0
        self.filter_text = ""
        self.list_scroll_offset = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="pane_choice_box"):
            yield Static(f"[bold]{self.title}[/]", id="choice_title")
            yield Static("", id="pane_filter", markup=False)
            yield Static("", id="pane_choice_body")
            yield Static(
                "[dim]type to filter, ctrl+c clear filter, up/down window, left/right or tab pane, enter select, esc cancel[/]",
                id="pane_choice_hint",
            )

    def on_mount(self) -> None:
        self._refresh_body()

    def _pane_search_text(self, pane: PaneRef) -> str:
        return " ".join(
            [
                pane.pane_id,
                pane.target,
                pane.window_name,
                pane.command,
                str(pane.cwd),
            ]
        ).lower()

    @staticmethod
    def _parse_target_parts(target: str) -> tuple[str, int, int]:
        text = target.strip()
        session = ""
        window_idx = 0
        pane_idx = 0
        try:
            sw, pane_part = text.rsplit(".", 1)
            pane_idx = int(pane_part)
        except ValueError:
            sw = text
        try:
            session, win_part = sw.split(":", 1)
            window_idx = int(win_part)
        except ValueError:
            session = sw
        return session, window_idx, pane_idx

    @staticmethod
    def _window_key(pane: PaneRef) -> str:
        return pane.target.rsplit(".", 1)[0]

    def _window_sort_key(self, window_key: str) -> tuple[str, int, str]:
        session = ""
        window_idx = 0
        try:
            session, win = window_key.split(":", 1)
            window_idx = int(win)
        except ValueError:
            session = window_key
        return (session, window_idx, window_key)

    def _pane_sort_key(self, pane: PaneRef) -> tuple[int, str]:
        _session, _win, pane_idx = self._parse_target_parts(pane.target)
        return (pane_idx, pane.target)

    def _visible_panes(self) -> list[PaneRef]:
        q = self.filter_text.strip().lower()
        if not q:
            return list(self.panes)

        ranked: list[tuple[float, PaneRef]] = []
        for pane in self.panes:
            text = self._pane_search_text(pane)
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
                ranked.append((score, pane))

        ranked.sort(key=lambda item: (-item[0], item[1].target, item[1].pane_id))
        return [pane for _score, pane in ranked]

    def _visible_window_groups(self) -> list[tuple[str, list[PaneRef], str]]:
        panes = self._visible_panes()
        grouped: dict[str, list[PaneRef]] = {}
        window_names: dict[str, str] = {}
        for pane in panes:
            key = self._window_key(pane)
            grouped.setdefault(key, []).append(pane)
            if key not in window_names:
                window_names[key] = pane.window_name

        out: list[tuple[str, list[PaneRef], str]] = []
        for key in sorted(grouped.keys(), key=self._window_sort_key):
            panes_for_window = sorted(grouped[key], key=self._pane_sort_key)
            out.append((key, panes_for_window, window_names.get(key, "-")))
        return out

    def _normalize_cursor(
        self, groups: list[tuple[str, list[PaneRef], str]]
    ) -> None:
        if not groups:
            self.row_index = 0
            self.col_index = 0
            self.list_scroll_offset = 0
            return
        if self.row_index >= len(groups):
            self.row_index = len(groups) - 1
        if self.row_index < 0:
            self.row_index = 0
        panes = groups[self.row_index][1]
        if not panes:
            self.col_index = 0
        else:
            if self.col_index >= len(panes):
                self.col_index = len(panes) - 1
            if self.col_index < 0:
                self.col_index = 0

    def _refresh_body(self) -> None:
        self.query_one("#pane_filter", Static).update(
            f"filter: {self.filter_text or '(all)'}"
        )
        groups = self._visible_window_groups()
        lines: list[str] = []

        def esc(value: str) -> str:
            return value.replace("[", "\\[").replace("]", "\\]")

        def trunc(value: str, width: int) -> str:
            text = value.strip()
            if len(text) <= width:
                return text
            if width <= 3:
                return text[:width]
            return text[: width - 3] + "..."

        if not groups:
            self.row_index = 0
            self.col_index = 0
            self.list_scroll_offset = 0
            lines.append("(no panes match current filter)")
            self.query_one("#pane_choice_body", Static).update("\n".join(lines))
            return

        self._normalize_cursor(groups)

        max_rows = 12
        max_offset = max(0, len(groups) - max_rows)
        if self.list_scroll_offset > max_offset:
            self.list_scroll_offset = max_offset
        if self.row_index < self.list_scroll_offset:
            self.list_scroll_offset = self.row_index
        elif self.row_index >= self.list_scroll_offset + max_rows:
            self.list_scroll_offset = self.row_index - max_rows + 1

        window = groups[
            self.list_scroll_offset : self.list_scroll_offset + max_rows
        ]
        for i, (window_key, panes, window_name) in enumerate(window):
            absolute_i = self.list_scroll_offset + i
            row_cursor = (
                f"[bold {COLOR_ACCENT_HEX}]>[/]"
                if absolute_i == self.row_index
                else " "
            )
            header = (
                f"{row_cursor} "
                f"[cyan]{esc(trunc(window_name, 18))}[/] "
                f"[dim]({esc(window_key)})[/]"
            )
            cells: list[str] = []
            cwd_variants = {str(p.cwd) for p in panes}
            show_cwd_suffix = len(cwd_variants) > 1
            for j, pane in enumerate(panes):
                _s, _w, pane_idx = self._parse_target_parts(pane.target)
                selected_cell = absolute_i == self.row_index and j == self.col_index
                cmd = trunc(pane.command or "-", 12)
                cwd_name = trunc(pane.cwd.name or str(pane.cwd), 16)
                label = f"{pane_idx}:{cmd}"
                if show_cwd_suffix:
                    label += f"@{cwd_name}"
                if selected_cell:
                    cell = f"[bold {COLOR_ACCENT_HEX}]{esc(label)}[/]"
                else:
                    cell = esc(label)
                cells.append(cell)
            lines.append(f"{header}\n    " + " [dim]|[/] ".join(cells))

        if len(groups) > max_rows:
            start = self.list_scroll_offset + 1
            end = self.list_scroll_offset + len(window)
            lines.append(f"showing windows {start}-{end} of {len(groups)}")

        current = groups[self.row_index][1][self.col_index]
        lines.append("")
        lines.append(
            f"[cyan]selected[/]: {esc(current.window_name)} [dim]({esc(self._window_key(current))})[/] {esc(str(current.cwd))}:{esc(current.command)}"
        )

        self.query_one("#pane_choice_body", Static).update("\n".join(lines))

    def on_key(self, event: Key) -> None:
        if event.key == "backspace":
            self.filter_text = self.filter_text[:-1]
            self.row_index = 0
            self.col_index = 0
            self.list_scroll_offset = 0
            self._refresh_body()
            event.stop()
            return
        if len(event.key) == 1 and event.key.isprintable() and event.key != " ":
            self.filter_text += event.key
            self.row_index = 0
            self.col_index = 0
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
        groups = self._visible_window_groups()
        if not groups:
            return
        self.row_index = (self.row_index - 1) % len(groups)
        self._normalize_cursor(groups)
        self._refresh_body()

    def action_move_down(self) -> None:
        groups = self._visible_window_groups()
        if not groups:
            return
        self.row_index = (self.row_index + 1) % len(groups)
        self._normalize_cursor(groups)
        self._refresh_body()

    def action_move_left(self) -> None:
        groups = self._visible_window_groups()
        if not groups:
            return
        panes = groups[self.row_index][1]
        if not panes:
            return
        self.col_index = (self.col_index - 1) % len(panes)
        self._refresh_body()

    def action_move_right(self) -> None:
        groups = self._visible_window_groups()
        if not groups:
            return
        panes = groups[self.row_index][1]
        if not panes:
            return
        self.col_index = (self.col_index + 1) % len(panes)
        self._refresh_body()

    def action_accept(self) -> None:
        groups = self._visible_window_groups()
        if not groups:
            self.dismiss(None)
            return
        self._normalize_cursor(groups)
        pane = groups[self.row_index][1][self.col_index]
        self.dismiss(pane.pane_id)

    def action_cancel(self) -> None:
        self.dismiss(None)
