from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.events import Key
from textual.widgets import Input, Static

from ...config.prefs import load_saved_filter_queries, save_filter_query
from ...core.constants import ACTION_ACCEPT, ACTION_CANCEL, SUFFIXES
from ...core.models import ProjectRow
from ...workspace.rows import compile_filter_expr
from ..screens.basic import InputScreen
from ..widgets import TokenFilterSuggester
from .base import LargeModalScreen

_BASE_DIR: Path | None = None


def set_filter_query_base_dir(base_dir: Path) -> None:
    global _BASE_DIR
    _BASE_DIR = base_dir


def _require_base_dir() -> Path:
    if _BASE_DIR is None:
        raise RuntimeError("filter query base dir not initialized")
    return _BASE_DIR


class FilterQueryScreen(LargeModalScreen[str | None]):
    CSS = """
    FilterQueryScreen #filter_stats { height: 1fr; overflow-y: auto; }
    """
    BINDINGS = [
        Binding("ctrl+s", "save_query", "Save query", show=False),
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
        Binding("enter", ACTION_ACCEPT, "Apply", show=False),
        Binding("escape", ACTION_CANCEL, "Cancel", show=False),
    ]

    def __init__(
        self,
        initial: str,
        tags: list[tuple[str, int]],
        props: list[tuple[str, int]],
        rows: list[ProjectRow],
    ) -> None:
        super().__init__()
        self.initial = initial
        self.tags = tags
        self.props = props
        self.rows = rows
        self.named, self.saved = load_saved_filter_queries(_require_base_dir())
        self.complete_index = -1
        self.complete_candidates: list[str] = []
        self.complete_head = ""
        self.complete_tail = ""
        self._skip_changed_resets = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_box"):
            yield Static("[bold]Filter query[/]")
            yield Input(
                value=self.initial,
                placeholder="#tag !property :tags=0 :created<=2025 (A OR B)",
                id="filter_query",
                suggester=TokenFilterSuggester(self._completion_candidates),
                compact=True,
            )
            yield Static("", id="filter_hint")
            yield Static("", id="filter_stats")
            yield self.hotkey_footer(
                [
                    ("tab", "complete"),
                    ("shift+tab", "prev completion"),
                    ("ctrl+s", "save query"),
                    ("enter", "apply"),
                    ("esc", "cancel"),
                ]
            )

    def on_mount(self) -> None:
        self.query_one("#filter_query", Input).focus()
        self._refresh()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter_query":
            if self._skip_changed_resets > 0:
                self._skip_changed_resets -= 1
            else:
                self.complete_index = -1
                self.complete_candidates = []
                self.complete_head = ""
                self.complete_tail = ""
            self._refresh()

    def on_key(self, event: Key) -> None:
        # Extra safety for terminals that alias tab / shift+tab.
        if event.key == "ctrl+i":
            self.action_next_completion()
            event.stop()
            return
        if event.key == "backtab":
            self.action_prev_completion()
            event.stop()
            return

    def _refresh(self) -> None:
        expr = self.query_one("#filter_query", Input).value.strip()
        pred, err = compile_filter_expr(expr)
        if err:
            hint = f"[bold red]{err}[/]"
        else:
            hint = "[bold cyan]logic:[/] AND by default, OR via [bold]OR[/], parentheses supported"
        self.query_one("#filter_hint", Static).update(hint)

        matched = sum(1 for r in self.rows if pred(r)) if not err else 0
        top_tags = ", ".join(f"#{t}({c})" for t, c in self.tags[:12]) or "-"
        top_props = ", ".join(f"!{p}({c})" for p, c in self.props[:12]) or "-"
        saved_named = ", ".join(sorted(self.named.keys())[:8]) or "-"
        self.query_one("#filter_stats", Static).update(
            "\n".join(
                [
                    f"rows: {matched}/{len(self.rows)}",
                    f"top tags: {top_tags}",
                    f"top properties: {top_props}",
                    f"saved names: {saved_named}",
                    "tab: cycle completions for current token, shift+tab reverse, right-arrow accepts gray suggestion",
                    "examples: #backend !git :tags>2 :created<=2025 (#api OR #web), @recent-web",
                ]
            )
        )

    @staticmethod
    def token_bounds_static(value: str) -> tuple[int, int, str]:
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

    def _token_bounds(self, value: str) -> tuple[int, int, str]:
        return self.token_bounds_static(value)

    def _completion_candidates(self, token: str) -> list[str]:
        t = token.strip()
        tags = [f"#{name}" for name, _ in self.tags]
        props = [f"!{key}" for key, _ in self.props]
        names = [f"@{name}" for name in sorted(self.named.keys())]
        suffixes = [f".{s}" for s in SUFFIXES]
        misc = [
            ":tags=0",
            ":tags>4",
            ":properties=0",
            ":properties>0",
            ":created=@-3y",
            ":created=@-2y100d",
            ":created=@-2y20m",
            ":modified=@-7d",
            ":active=@-30d",
            ":created=2025",
            ":created=2025-01",
            ":created=2025-01-05",
            ":created<=2025",
            ":created=@-1w",
            "OR",
            "(",
            ")",
        ]

        if not t:
            return names + tags[:40] + props[:40] + misc
        if t.startswith("#"):
            return [x for x in tags if x.lower().startswith(t.lower())][:100]
        if t.startswith("!"):
            return [x for x in props if x.lower().startswith(t.lower())][:100]
        if t.startswith("@"):
            return [x for x in names if x.lower().startswith(t.lower())][:100]
        return [
            x
            for x in (names + tags + props + suffixes + misc)
            if x.lower().startswith(t.lower())
        ][:100]

    def _apply_completion(self, forward: bool) -> None:
        inp = self.query_one("#filter_query", Input)
        if self.complete_index < 0 or not self.complete_candidates:
            value = inp.value
            start, end, token = self._token_bounds(value)
            candidates = self._completion_candidates(token)
            if not candidates:
                return
            self.complete_candidates = candidates
            self.complete_head = value[:start]
            self.complete_tail = value[end:]
            self.complete_index = 0 if forward else len(candidates) - 1
        else:
            candidates = self.complete_candidates
            if forward:
                self.complete_index = (self.complete_index + 1) % len(candidates)
            else:
                self.complete_index = (self.complete_index - 1) % len(candidates)
        replacement = candidates[self.complete_index]
        new_value = self.complete_head + replacement + self.complete_tail
        self._skip_changed_resets += 1
        inp.value = new_value
        inp.cursor_position = len(new_value)
        self._refresh()

    def action_next_completion(self) -> None:
        self._apply_completion(True)

    def action_prev_completion(self) -> None:
        self._apply_completion(False)

    def action_save_query(self) -> None:
        expr = self.query_one("#filter_query", Input).value.strip()
        if not expr:
            self.query_one("#filter_hint", Static).update(
                "[bold yellow]empty query not saved[/]"
            )
            return
        self.app.push_screen(
            InputScreen("Save filter name (optional)", "recent-web"),
            lambda name: self._on_save_filter_name(name, expr),
        )

    def _on_save_filter_name(self, name: str | None, expr: str) -> None:
        save_filter_query(_require_base_dir(), expr, name=name)
        self.named, self.saved = load_saved_filter_queries(_require_base_dir())
        if name and name.strip():
            self.query_one("#filter_hint", Static).update(
                f"[bold green]saved as @{name.strip()}[/]"
            )
        else:
            self.query_one("#filter_hint", Static).update(
                "[bold green]saved to filters.saved[/]"
            )
        self._refresh()

    def action_accept(self) -> None:
        expr = self.query_one("#filter_query", Input).value.strip()
        if expr.startswith("@") and len(expr) > 1:
            resolved = self.named.get(expr[1:].strip())
            if not resolved:
                self.query_one("#filter_hint", Static).update(
                    "[bold red]unknown saved filter name[/]"
                )
                return
            expr = resolved
        _pred, err = compile_filter_expr(expr)
        if err:
            self.query_one("#filter_hint", Static).update(f"[bold red]{err}[/]")
            return
        self.dismiss(expr)

    def action_cancel(self) -> None:
        self.dismiss(None)
