from __future__ import annotations

from textual.app import App, ComposeResult
from textual.widgets import Static


class _Hello(App[None]):
    def compose(self) -> ComposeResult:
        yield Static("hi", id="greeting")


async def test_pilot_smoke_app_mounts() -> None:
    app = _Hello()
    async with app.run_test() as pilot:
        await pilot.pause()
        widget = app.query_one("#greeting", Static)
        assert str(widget.render()) == "hi"
