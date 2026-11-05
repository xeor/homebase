"""`b new` without inputs: only the new-project popup.

The full TUI loads the project list, probes panes and refreshes the cache
before the popup appears. This app shows the popup alone and reuses the
TUI's submit flow (create, hooks, open), so the result is the same."""
from __future__ import annotations

import sys
from pathlib import Path

from textual.app import App
from textual.notifications import SeverityLevel

from ..core.constants import MODE_ACTIVE
from ..hooks.runtime import HookRunRecord
from .actions import project_create
from .context import UIContext, build_ui_context
from .screens.new_project import NewProjectScreen


class NewProjectApp(App[tuple[str, Path | None, list[str]]]):
    """Implements the part of BApp that `project_create` and the hook
    runtime use."""

    def __init__(self, base_dir: Path, ctx: UIContext | None = None) -> None:
        super().__init__()
        self.base_dir = base_dir
        self.ctx = ctx if ctx is not None else build_ui_context(base_dir)
        self.start_new_mode = True
        self.view_mode = MODE_ACTIVE
        self.hook_running: dict[str, float] = {}
        self.hook_recent: dict[tuple[str, str], list[HookRunRecord]] = {}
        self._busy_depth = 0
        self.messages: list[tuple[str, str]] = []
        self.runtime_errors: list[str] = []
        self.last_new_summary: str | None = None
        self.last_new_error: str | None = None

    def on_mount(self) -> None:
        self.push_screen(
            NewProjectScreen(self.base_dir, allow_stay_in_b=False),
            self._on_new_project_submit,
        )

    def _on_new_project_submit(self, payload: dict[str, object] | None) -> None:
        project_create.on_new_project_submit(self, payload, base_dir=self.base_dir)

    def _log(self, msg: str, level: str = "info") -> None:  # type: ignore[override]  # textual.App._log is internal logging unused here
        self.messages.append((level, msg))

    def _show_runtime_error(
        self, context: str, exc: BaseException, traceback_tail: str = ""
    ) -> None:
        text = f"{context}: {type(exc).__name__}: {str(exc).strip() or '(no message)'}"
        self.runtime_errors.append(f"{text}\n{traceback_tail}".strip())

    def _set_runtime_status(
        self, text: str, level: str = "info", ttl_s: float = 12.0
    ) -> None:
        severity: SeverityLevel = (
            "warning" if level == "warn" else "error" if level == "error" else "information"
        )
        self.notify(text, severity=severity, timeout=ttl_s)

    def _busy_start(self, label: str) -> None:
        self._busy_depth += 1
        self.sub_title = label

    def _busy_stop(self) -> None:
        self._busy_depth = max(0, self._busy_depth - 1)
        if not self._busy_depth:
            self.sub_title = ""

    def _refresh_side(self) -> None:
        """No side panel here."""


def run_new_project_ui(
    base_dir: Path,
    cwd: Path,
    ctx: UIContext | None = None,
    start_new: bool = True,
    initial_filter_expr: str = "",
) -> tuple[str, Path | None, list[str]]:
    """Same signature and result as `run_textual_ui(start_new=True)`."""
    del cwd, start_new, initial_filter_expr
    app = NewProjectApp(base_dir, ctx=ctx)
    result = app.run() or ("quit", None, [])
    if app.last_new_summary:
        print(app.last_new_summary)
    for error in app.runtime_errors:
        print(error, file=sys.stderr)
    if app.last_new_error:
        print(f"b new failed:\n{app.last_new_error}", file=sys.stderr)
    return result
