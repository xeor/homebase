from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SetupSelectableFix:
    id: str
    title: str
    selected: bool = True
    status: str = ""
    details: str = ""
    changes: str = ""
    preview: str = ""


def select_fix_ids_textual(fixes: list[SetupSelectableFix]) -> set[str] | None:
    try:
        from textual.app import App, ComposeResult
        from textual.binding import Binding
        from textual.widgets import Footer, Header, SelectionList
    except ImportError:
        return None

    class _SetupSelectApp(App[set[str] | None]):
        CSS = """
        Screen { align: center middle; }
        #panel { width: 92%; height: 90%; border: round $accent; }
        #title { padding: 1 2; text-style: bold; }
        #hint { padding: 0 2 1 2; color: $text-muted; }
        #body { height: 1fr; }
        #left { width: 1fr; border: round $panel; }
        #right { width: 1fr; border: round $panel; padding: 0 1; }
        SelectionList { height: 1fr; }
        #detail_title { text-style: bold; padding: 0 0 1 0; }
        #detail_block { padding: 0 0 1 0; }
        #preview_title { text-style: bold; padding: 1 0 0 0; }
        #preview_block { padding: 0 0 1 0; color: $text-muted; }
        """
        BINDINGS = [
            Binding("enter", "apply", "Apply selected"),
            Binding("q", "cancel", "Cancel"),
            Binding("a", "all", "Select all"),
            Binding("n", "none", "Select none"),
        ]

        def compose(self) -> ComposeResult:
            from textual.containers import Horizontal, Vertical
            from textual.widgets import Static

            yield Header(show_clock=False)
            with Vertical(id="panel"):
                yield Static("Setup fixes: select actions to apply", id="title")
                with Horizontal(id="body"):
                    rows = [(fix.title, fix.id, fix.selected) for fix in fixes]
                    yield SelectionList[str](*rows, id="fixes")
                    with Vertical(id="right"):
                        yield Static("Fix details", id="detail_title")
                        yield Static("", id="detail_block")
                        yield Static("Preview", id="preview_title")
                        yield Static("", id="preview_block")
                yield Static(
                    "Keys: ↑/↓ move, space toggle, a all, n none, enter apply, q cancel",
                    id="hint",
                )
            yield Footer()

        def on_mount(self) -> None:
            self._refresh_detail()

        def on_selection_list_selection_toggled(self, _event) -> None:
            self._refresh_detail()

        def on_option_list_option_highlighted(self, _event) -> None:
            self._refresh_detail()

        def _refresh_detail(self) -> None:
            from textual.widgets import Static

            widget = self.query_one("#fixes", SelectionList)
            current = widget.highlighted
            detail = self.query_one("#detail_block", Static)
            preview = self.query_one("#preview_block", Static)
            if current is None:
                detail.update("No fix selected.")
                preview.update("")
                return
            selected_id = str(current)
            match = next((item for item in fixes if item.id == selected_id), None)
            if match is None:
                detail.update("No fix selected.")
                preview.update("")
                return
            lines = [
                f"What: {match.title}",
                f"Status: {match.status or 'pending'}",
                f"Will change: {match.changes or 'n/a'}",
            ]
            if match.details:
                lines.append("")
                lines.append(match.details)
            detail.update("\n".join(lines))
            preview.update(match.preview or "<no diff available>")

        def action_apply(self) -> None:
            widget = self.query_one("#fixes", SelectionList)
            selected = {str(value) for value in widget.selected}
            self.exit(selected)

        def action_cancel(self) -> None:
            self.exit(None)

        def action_all(self) -> None:
            widget = self.query_one("#fixes", SelectionList)
            widget.select_all()

        def action_none(self) -> None:
            widget = self.query_one("#fixes", SelectionList)
            widget.deselect_all()

    app = _SetupSelectApp()
    return app.run()


__all__ = ["SetupSelectableFix", "select_fix_ids_textual"]
