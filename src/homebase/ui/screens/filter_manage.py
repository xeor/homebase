from __future__ import annotations

import re
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Click, Key, Resize
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from ...config.prefs import (
    delete_named_filter,
    load_saved_filter_queries,
    resolve_named_filters_for_display,
    save_filter_query,
)
from ...core.constants import SUFFIXES
from ...core.models import ProjectRow
from ...core.utils import WIDGET_API_ERRORS
from ...workspace.rows import (
    _FILTER_TOKEN_RE,
    compile_filter_expr,
    normalize_filter_expression,
    pretty_filter_expression,
)
from ..screens.basic import ConfirmScreen, InputScreen
from ..screens.listwin import compute_window, overflow_hint
from ..widgets import TokenFilterSuggester

_BASE_DIR: Path | None = None


def set_filter_manage_base_dir(base_dir: Path) -> None:
    global _BASE_DIR
    _BASE_DIR = base_dir


def _require_base_dir() -> Path:
    if _BASE_DIR is None:
        raise RuntimeError("filter manage base dir not initialized")
    return _BASE_DIR


class FilterManageScreen(ModalScreen[str | None]):
    CSS = """
    Screen { align: center middle; }
    #filter_mgmt_box { width: 100%; height: 100%; border: round $accent; background: $surface; padding: 1 2; }
    #filter_mgmt_body_wrap { height: 1fr; }
    #filter_mgmt_left { width: 2fr; border: round $surface-lighten-1; padding: 0 1; }
    #filter_mgmt_right { width: 1fr; border: round $surface-lighten-1; padding: 0 1; }
    #filter_mgmt_body { height: 1fr; }
    """
    BINDINGS = [
        ("up", "move_up", "Up"),
        ("down", "move_down", "Down"),
        ("space", "toggle", "Toggle"),
        Binding(
            "tab", "next_completion", "Next completion", show=False, priority=True
        ),
        Binding(
            "shift+tab",
            "prev_completion",
            "Prev completion",
            show=False,
            priority=True,
        ),
        ("ctrl+i", "next_completion", "Next completion"),
        ("ctrl+shift+i", "prev_completion", "Prev completion"),
        Binding("ctrl+f", "back", "Back", show=False, priority=True),
        ("ctrl+s", "save_current", "Save current"),
        ("ctrl+e", "edit_selected", "Edit selected"),
        ("ctrl+x", "delete_selected", "Delete selected"),
        Binding("enter", "toggle_focus", "Toggle focus", show=False, priority=True),
        Binding("escape", "back", "Back", show=False, priority=True),
    ]

    def __init__(
        self, current_filter_expr: str, current_query: str, rows: list[ProjectRow]
    ) -> None:
        super().__init__()
        self.current_filter_expr = current_filter_expr
        self.current_query = current_query
        self.rows = rows
        self.named, _saved = load_saved_filter_queries(_require_base_dir())
        self.names = sorted(self.named.keys())
        self.index = 0
        self.focus_section = 0  # 0=input, 1=list
        self.selected: set[str] = set()
        for tok in _FILTER_TOKEN_RE.findall(current_filter_expr):
            if tok.startswith("@") and tok[1:] in self.named:
                self.selected.add(tok[1:])
        self.complete_index = -1
        self.complete_candidates: list[str] = []
        self.complete_head = ""
        self.complete_tail = ""
        self._skip_changed_resets = 0
        self.list_scroll_offset = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="filter_mgmt_box"):
            yield Static("[bold]Saved filters[/]")
            with Horizontal(id="filter_mgmt_body_wrap"):
                with Vertical(id="filter_mgmt_left"):
                    yield Input(
                        value=normalize_filter_expression(self.current_query),
                        placeholder="extra filter expression (!prop #tag tags=0 created<=2025 ...)",
                        id="filter_mgmt_input",
                        suggester=TokenFilterSuggester(
                            self._completion_candidates_for_input
                        ),
                        compact=True,
                    )
                    yield Static("", id="filter_mgmt_body", markup=False)
                with VerticalScroll(id="filter_mgmt_right"):
                    yield Static("", id="filter_mgmt_active")
            yield Static("", id="filter_mgmt_hint")

    def on_mount(self) -> None:
        self.query_one("#filter_mgmt_input", Input).focus()
        self._set_focus_section()
        self._refresh()

    def on_resize(self, _event: Resize) -> None:
        self._refresh()

    def _set_focus_section(self) -> None:
        inp = self.query_one("#filter_mgmt_input", Input)
        if self.focus_section == 0:
            if hasattr(inp, "select_on_focus"):
                try:
                    inp.select_on_focus = False
                except WIDGET_API_ERRORS:
                    pass
            if hasattr(inp, "select_all_on_focus"):
                try:
                    inp.select_all_on_focus = False
                except WIDGET_API_ERRORS:
                    pass
            inp.focus()
            try:
                inp.cursor_position = len(inp.value)
            except WIDGET_API_ERRORS:
                pass
        else:
            inp.blur()

    def action_next_section(self) -> None:
        self.focus_section = (self.focus_section + 1) % 2
        self._set_focus_section()
        self._refresh()

    def action_prev_section(self) -> None:
        self.focus_section = (self.focus_section - 1) % 2
        self._set_focus_section()
        self._refresh()

    def action_toggle_focus(self) -> None:
        self.action_next_section()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "filter_mgmt_input":
            return
        if self._skip_changed_resets > 0:
            self._skip_changed_resets -= 1
        else:
            self.complete_index = -1
            self.complete_candidates = []
            self.complete_head = ""
            self.complete_tail = ""
        self._refresh()

    def on_click(self, event: Click) -> None:
        wid = event.widget
        wid_id = getattr(wid, "id", "") or ""
        if wid_id == "filter_mgmt_input":
            self.focus_section = 0
        elif wid_id in {"filter_mgmt_body", "filter_mgmt_left"}:
            self.focus_section = 1
        self._set_focus_section()

    def on_key(self, event: Key) -> None:
        if self.focus_section != 0:
            return
        if event.key in {"ctrl+i", "tab"}:
            self.action_next_completion()
            event.stop()
            return
        if event.key in {"ctrl+shift+i", "backtab", "shift+tab"}:
            self.action_prev_completion()
            event.stop()
            return

    def _initial_manual_expr(self) -> str:
        toks = _FILTER_TOKEN_RE.findall(self.current_query.strip())
        kept: list[str] = []
        for t in toks:
            if t.startswith("@") and t[1:] in self.named:
                continue
            kept.append(t)
        out = " ".join(kept).strip()
        out = re.sub(r"\bOR\b\s*$", "", out, flags=re.IGNORECASE).strip()
        out = re.sub(r"^\s*\bOR\b", "", out, flags=re.IGNORECASE).strip()
        return out

    def _manual_expr_from_input(self) -> str:
        raw = self.query_one("#filter_mgmt_input", Input).value.strip()
        toks = _FILTER_TOKEN_RE.findall(raw)
        kept: list[str] = []
        for t in toks:
            if t.startswith("@") and t[1:] in self.named:
                continue
            kept.append(t)
        out = " ".join(kept).strip()
        return normalize_filter_expression(out)

    def _rewrite_input_from_selection(self) -> None:
        saved_part = " OR ".join(f"@{name}" for name in sorted(self.selected))
        manual = self._manual_expr_from_input()
        expr = (
            f"({saved_part}) {manual}".strip()
            if saved_part and manual
            else (saved_part or manual)
        )
        expr = normalize_filter_expression(expr)
        self._skip_changed_resets += 1
        inp = self.query_one("#filter_mgmt_input", Input)
        inp.value = expr
        inp.cursor_position = len(expr)

    def _composed_expr(self) -> str:
        return normalize_filter_expression(
            self.query_one("#filter_mgmt_input", Input).value.strip()
        )

    def _render_colored_expr(self, expr: str) -> str:
        out_lines: list[str] = []
        for line in expr.splitlines():
            leading = len(line) - len(line.lstrip(" "))
            pad = " " * leading
            body = line[leading:]
            parts: list[str] = []
            for tok in _FILTER_TOKEN_RE.findall(body):
                if tok.startswith("#"):
                    parts.append(f"[cyan]{tok}[/]")
                elif tok.startswith("!"):
                    parts.append(f"[magenta]{tok}[/]")
                elif tok.startswith("."):
                    parts.append(f"[blue]{tok}[/]")
                elif tok.startswith("@"):
                    parts.append(f"[green]{tok}[/]")
                elif re.match(
                    r"^(?:(?:created|opened|last)=@-(?:\d+[ymwdhs])+|(?:tags|props|properties)(?:<=|>=|!=|=|<|>)\d+|(?:created|opened|last)(?:<=|>=|!=|=|<|>)\d{4}(?:-\d{2}(?:-\d{2})?)?)$",
                    tok.lower(),
                ):
                    parts.append(f"[yellow]{tok}[/]")
                elif tok in {"OR", "|"}:
                    parts.append(f"[bold yellow]{tok}[/]")
                else:
                    parts.append(tok)
            out_lines.append(f"{pad}{' '.join(parts)}".rstrip())
        return "\n".join(out_lines)

    @staticmethod
    def _token_bounds(value: str) -> tuple[int, int, str]:
        if not value:
            return 0, 0, ""
        end = len(value)
        i = end - 1
        while i >= 0 and value[i].isspace():
            i -= 1
        if i < 0:
            return end, end, ""
        end = i + 1
        start = i
        while start >= 0 and not value[start].isspace():
            start -= 1
        start += 1
        return start, end, value[start:end]

    def _completion_candidates_for_input(self, token: str) -> list[str]:
        t = token.strip()
        tag_counts: dict[str, int] = {}
        prop_counts: dict[str, int] = {}
        for row in self.rows:
            for tg in row.tags:
                tag_counts[tg] = tag_counts.get(tg, 0) + 1
            for p in row.properties:
                prop_counts[p] = prop_counts.get(p, 0) + 1
        tags = [
            f"#{x}"
            for x, _c in sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        props = [
            f"!{x}"
            for x, _c in sorted(prop_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        names = [f"@{n}" for n in sorted(self.named.keys())]
        suffixes = [f".{s}" for s in SUFFIXES]
        misc = [
            "tags=0",
            "tags>4",
            "props=0",
            "props>0",
            ":created=@-3y",
            ":created=@-2y100d",
            ":created=@-2y20m",
            ":last=@-7d",
            ":created=2025",
            ":created=2025-01",
            ":created=2025-01-05",
            ":created<=2025",
            ":created=@-1w",
            "OR",
            "(",
            ")",
        ]
        pool = names + tags + props + suffixes + misc
        if not t:
            return pool[:120]
        return [x for x in pool if x.lower().startswith(t.lower())][:120]

    def _apply_completion(self, forward: bool) -> None:
        inp = self.query_one("#filter_mgmt_input", Input)
        if self.complete_index < 0 or not self.complete_candidates:
            value = inp.value
            start, end, token = self._token_bounds(value)
            cands = self._completion_candidates_for_input(token)
            if not cands:
                return
            self.complete_candidates = cands
            self.complete_head = value[:start]
            self.complete_tail = value[end:]
            self.complete_index = 0 if forward else len(cands) - 1
        else:
            cands = self.complete_candidates
            if forward:
                self.complete_index = (self.complete_index + 1) % len(cands)
            else:
                self.complete_index = (self.complete_index - 1) % len(cands)
        replacement = cands[self.complete_index]
        new_value = self.complete_head + replacement + self.complete_tail
        self._skip_changed_resets += 1
        inp.value = new_value
        inp.cursor_position = len(new_value)
        self._refresh()

    def action_next_completion(self) -> None:
        if self.focus_section != 0:
            return
        self._apply_completion(True)

    def action_prev_completion(self) -> None:
        if self.focus_section != 0:
            return
        self._apply_completion(False)

    def _refresh(self) -> None:
        expr_now = self.query_one("#filter_mgmt_input", Input).value.strip()
        selected_from_expr = {
            t[1:]
            for t in _FILTER_TOKEN_RE.findall(expr_now)
            if t.startswith("@") and t[1:] in self.named
        }
        self.selected = set(selected_from_expr)
        body = self.query_one("#filter_mgmt_body", Static)
        lines: list[str] = []
        if not self.names:
            lines.append("(no named filters)")
            self.list_scroll_offset = 0
        else:
            if self.index < 0:
                self.index = 0
            elif self.index >= len(self.names):
                self.index = len(self.names) - 1
            offset, max_rows = compute_window(
                total=len(self.names),
                cursor=self.index,
                current_offset=self.list_scroll_offset,
                body_widget=body,
                reserve_bottom_rows=1,
            )
            self.list_scroll_offset = offset
            window = self.names[offset : offset + max_rows]
            for i, name in enumerate(window):
                absolute = offset + i
                cur = ">" if absolute == self.index else " "
                mark = "[x]" if name in self.selected else "[ ]"
                expr = self.named.get(name, "")
                preview = expr if len(expr) <= 64 else expr[:61] + "..."
                lines.append(f"{cur} {mark} @{name}  ::  {preview}")
            hint = overflow_hint(len(self.names), offset, len(window))
            if hint is not None:
                lines.append(hint)
        body.update("\n".join(lines))
        active_expr = self._composed_expr()
        resolved = resolve_named_filters_for_display(active_expr)
        pred, err = compile_filter_expr(active_expr)
        matched = sum(1 for r in self.rows if pred(r)) if not err else 0
        resolved_pretty = pretty_filter_expression(resolved)
        self.query_one("#filter_mgmt_active", Static).update(
            "\n".join(
                [
                    f"[bold yellow]active[/]: {self._render_colored_expr(active_expr or '-')}\n",
                    "[bold yellow]resolved[/]:",
                    self._render_colored_expr(resolved_pretty),
                    "",
                    f"rows: {matched}/{len(self.rows)}"
                    + (f"  [red]({err})[/]" if err else ""),
                ]
            )
        )
        self.query_one("#filter_mgmt_hint", Static).update(
            "enter switch input/list  tab complete(input)  shift+tab reverse  space toggle(list)\n"
            "esc/ctrl+f go back/apply  ctrl+s save  ctrl+e edit  ctrl+x delete\n"
            "selected filters are OR-ed together; query text still AND applies"
        )

    def action_move_up(self) -> None:
        if self.focus_section != 1:
            return
        if not self.names:
            return
        self.index = (self.index - 1) % len(self.names)
        self._refresh()

    def action_move_down(self) -> None:
        if self.focus_section != 1:
            return
        if not self.names:
            return
        self.index = (self.index + 1) % len(self.names)
        self._refresh()

    def action_toggle(self) -> None:
        if self.focus_section != 1:
            return
        if not self.names:
            return
        name = self.names[self.index]
        if name in self.selected:
            self.selected.remove(name)
        else:
            self.selected.add(name)
        self._rewrite_input_from_selection()
        self._refresh()

    def action_save_current(self) -> None:
        expr = self._composed_expr().strip()
        if not expr:
            self.query_one("#filter_mgmt_hint", Static).update(
                "[bold yellow]no active query/filter to save[/]"
            )
            return
        self.app.push_screen(
            InputScreen("Save filter name", "recent-web"),
            lambda name: self._on_save_name(name, expr),
        )

    def action_edit_selected(self) -> None:
        if not self.names:
            return
        name = self.names[self.index]
        expr = self.named.get(name, "")
        self.app.push_screen(
            InputScreen(f"Edit @{name}", "#tag !prop ...", value=expr),
            lambda new_expr: self._on_edit_expr(name, new_expr),
        )

    def _on_edit_expr(self, name: str, new_expr: str | None) -> None:
        expr = (new_expr or "").strip()
        if not expr:
            self.query_one("#filter_mgmt_hint", Static).update(
                "[bold yellow]edit cancelled[/]"
            )
            return
        save_filter_query(_require_base_dir(), expr, name=name)
        self.named, _saved = load_saved_filter_queries(_require_base_dir())
        self.names = sorted(self.named.keys())
        self.query_one("#filter_mgmt_hint", Static).update(
            f"[bold green]updated @{name}[/]"
        )
        self._refresh()

    def action_delete_selected(self) -> None:
        if not self.names:
            return
        name = self.names[self.index]
        self.app.push_screen(
            ConfirmScreen(
                f"Delete saved filter @{name}?",
                "[cyan]effect[/]: removes only the named filter entry\n"
                "[cyan]kept[/]: projects, tags, and saved history remain unchanged",
            ),
            lambda ok: self._on_delete_selected(name, ok),
        )

    def _on_delete_selected(self, name: str, ok: bool) -> None:
        if not ok:
            return
        removed = delete_named_filter(_require_base_dir(), name)
        if not removed:
            self.query_one("#filter_mgmt_hint", Static).update(
                f"[bold red]failed to delete @{name}[/]"
            )
            return
        self.named, _saved = load_saved_filter_queries(_require_base_dir())
        self.names = sorted(self.named.keys())
        self.selected.discard(name)
        if self.index >= len(self.names):
            self.index = max(0, len(self.names) - 1)
        self.query_one("#filter_mgmt_hint", Static).update(
            f"[bold green]deleted @{name}[/]"
        )
        self._refresh()

    def _on_save_name(self, name: str | None, expr: str) -> None:
        nm = (name or "").strip()
        if not nm:
            self.query_one("#filter_mgmt_hint", Static).update(
                "[bold yellow]save cancelled[/]"
            )
            return
        save_filter_query(_require_base_dir(), expr, name=nm)
        self.named, _saved = load_saved_filter_queries(_require_base_dir())
        self.names = sorted(self.named.keys())
        self.selected.add(nm)
        self.query_one("#filter_mgmt_hint", Static).update(
            f"[bold green]saved @{nm}[/]"
        )
        self._refresh()

    def action_back(self) -> None:
        expr = self._composed_expr().strip()
        pred, err = compile_filter_expr(expr)
        if err:
            self.query_one("#filter_mgmt_hint", Static).update(
                f"[bold red]{err}[/]"
            )
            return
        _ = pred
        self.dismiss(expr)

    def action_accept(self) -> None:
        self.action_toggle_focus()

    def action_cancel(self) -> None:
        self.action_back()
