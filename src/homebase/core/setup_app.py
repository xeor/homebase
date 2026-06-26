from __future__ import annotations

import shlex
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from rich.markup import escape

from .setup_model import (
    INTENT_ABSENT,
    INTENT_CANNOT_CREATE,
    INTENT_CANNOT_REMOVE,
    INTENT_CREATE,
    INTENT_KEEP,
    INTENT_REMOVE,
    STATUS_FAIL,
    STATUS_PASS,
    STATUS_SKIP,
    STATUS_WARN,
    ApplyOutcome,
    FixResult,
    MainThreadActivator,
    SetupCheck,
    SetupContext,
    SetupDebugOption,
    SetupDebugTool,
    SetupFix,
)

_STATUS_COLOR = {
    STATUS_PASS: "bright_green",
    STATUS_WARN: "bright_yellow",
    STATUS_FAIL: "bright_red",
    STATUS_SKIP: "bright_cyan",
}


def _status_marker(status: str) -> str:
    glyph = {
        STATUS_PASS: "✓",
        STATUS_WARN: "!",
        STATUS_FAIL: "✗",
        STATUS_SKIP: "-",
    }.get(status, "?")
    color = _STATUS_COLOR.get(status, "white")
    return f"[bold {color}]{glyph}[/]"


def _status_badge(status: str) -> str:
    color = _STATUS_COLOR.get(status, "white")
    return f"[bold {color}]{status}[/]"


_ACTION_COL_WIDTH = 7
_STATE_COL_WIDTH = 7
_TAG_COL_WIDTH = 11


def _fix_state_word(fix: SetupFix) -> tuple[str, str]:
    """(word, color) describing the current on-disk state."""
    if fix.currently_correct:
        return "ok", "bright_green"
    if fix.currently_present:
        return "stale", "bright_yellow"
    color = (
        "bright_red" if fix.required
        else ("bright_yellow" if fix.recommended else "bright_cyan")
    )
    return "missing", color


def _action_word_for_intent(intent: str) -> tuple[str, str]:
    """(word, color) for the action that ``intent`` represents."""
    return {
        INTENT_KEEP: ("keep", "bright_green"),
        INTENT_CREATE: ("add", "bright_green"),
        INTENT_REMOVE: ("remove", "bright_red"),
        INTENT_ABSENT: ("skip", "bright_black"),
        INTENT_CANNOT_CREATE: ("can't", "bright_red"),
        INTENT_CANNOT_REMOVE: ("can't", "bright_red"),
    }.get(intent, (intent, "white"))


def _right_pane_for_intent(
    fix: SetupFix, intent: str
) -> tuple[str, str]:
    """Return ``(title, body_markup)`` for the right-hand info pane.

    - For KEEP / ABSENT / CANNOT_* intents nothing will happen on
      apply, so the pane shows a status / verified message rather
      than a misleading "preview" diff.
    - For CREATE / REMOVE intents the pane shows the create / remove
      diff — what will actually change."""
    if intent == INTENT_KEEP:
        body_lines = [
            "[bold bright_green]✓ Already configured — nothing to change.[/]",
            "",
            "[bold]What was verified:[/]",
            f"  {fix.current_state_text or '<state unknown>'}",
        ]
        if fix.description:
            body_lines.append("")
            body_lines.append(fix.description)
        return "Verified", "\n".join(body_lines)
    if intent == INTENT_ABSENT:
        body_lines = [
            "[dim]· Not installed and not selected — no action.[/]",
            "",
            f"[bold]Current:[/] {fix.current_state_text or '<unknown>'}",
        ]
        if fix.description:
            body_lines.append("")
            body_lines.append(fix.description)
        return "Status", "\n".join(body_lines)
    if intent == INTENT_CANNOT_CREATE:
        return "Status", (
            "[bright_red]No installer wired up — this item must be "
            "configured manually.[/]"
        )
    if intent == INTENT_CANNOT_REMOVE:
        return "Status", (
            "[bright_red]Setup cannot uninstall this — remove it by "
            "hand if you really want to.[/]\n\n"
            f"[bold]Current:[/] {fix.current_state_text or '<unknown>'}"
        )
    if intent == INTENT_CREATE:
        body = (
            "\n".join(escape(line) for line in fix.preview_create)
            if fix.preview_create
            else "<no preview available>"
        )
        return "Preview · install", body
    if intent == INTENT_REMOVE:
        body = (
            "\n".join(escape(line) for line in fix.preview_remove)
            if fix.preview_remove
            else "<no preview available>"
        )
        return "Preview · remove", body
    return "Status", fix.current_state_text or ""


def _fix_state_text(fix: SetupFix) -> str:
    if fix.currently_correct:
        return "[bright_green]configured[/]"
    if fix.currently_present:
        return "[bright_yellow]present, needs update[/]"
    if fix.required:
        return "[bright_red]missing (required)[/]"
    if fix.recommended:
        return "[bright_yellow]missing (recommended)[/]"
    return "[bright_cyan]not installed (optional)[/]"


def _intent_label(intent: str) -> str:
    return {
        INTENT_KEEP: "[bright_green]keep[/]",
        INTENT_CREATE: "[bright_green]install[/]",
        INTENT_REMOVE: "[bright_red]REMOVE[/]",
        INTENT_ABSENT: "[bright_cyan]skip (not installed)[/]",
        INTENT_CANNOT_CREATE: "[bright_red]cannot install[/]",
        INTENT_CANNOT_REMOVE: "[bright_red]manual uninstall needed[/]",
    }.get(intent, intent)


def _check_groups() -> list[tuple[str, set[str]]]:
    return [
        ("Tools", {"uv", "git", "tmux", "tmuxp", "python_runtime"}),
        ("Install", {"self_update", "path", "b_launcher"}),
        ("Workspace", {"homebase_dir", "homebase_writable", "config", "gitignore"}),
        ("Shell integration", {"tmux_binding", "shell_completion", "shell_init"}),
    ]


def _format_overview(checks: list[SetupCheck]) -> str:
    if not checks:
        return "No checks."
    by_id = {c.id: c for c in checks}
    rows: list[str] = []
    seen: set[str] = set()
    for title, ids in _check_groups():
        group_checks = [by_id[cid] for cid in ids if cid in by_id]
        if not group_checks:
            continue
        rows.append(f"[bold underline]{title}[/]")
        for c in group_checks:
            seen.add(c.id)
            rows.append(f"  {_status_marker(c.status)} [bold]{c.name}[/]: {c.detail}")
            for line in c.extra_lines:
                rows.append(f"      {line.lstrip()}")
        rows.append("")
    leftovers = [c for c in checks if c.id not in seen]
    if leftovers:
        rows.append("[bold underline]Other[/]")
        for c in leftovers:
            rows.append(f"  {_status_marker(c.status)} [bold]{c.name}[/]: {c.detail}")
        rows.append("")
    pass_count = sum(1 for c in checks if c.status == STATUS_PASS)
    warn_count = sum(1 for c in checks if c.status == STATUS_WARN)
    fail_count = sum(1 for c in checks if c.status == STATUS_FAIL)
    rows.append(
        f"summary: [bold bright_green]PASS={pass_count}[/] "
        f"[bold bright_yellow]WARN={warn_count}[/] "
        f"[bold bright_red]FAIL={fail_count}[/]"
    )
    return "\n".join(rows)


def _format_self_update_static(ctx: SetupContext) -> str:
    lines: list[str] = [
        f"[bold]install method:[/] {escape(ctx.install_mode)} "
        f"({escape(ctx.update_detail)})",
        "",
    ]
    if ctx.update_cmd:
        lines.append("[bold bright_green]Self-update available[/]")
        lines.append(f"  command: [bold]{escape(ctx.update_cmd)}[/]")
        lines.append(f"  detail:  {escape(ctx.update_detail)}")
    else:
        lines.append("[bold bright_yellow]Self-update needs manual action[/]")
        lines.append(f"  detail:  {escape(ctx.update_detail) or '<unknown>'}")
    lines.append("")
    lines.append("[bold]Diagnostics:[/]")
    launcher = str(ctx.launcher_path) if ctx.launcher_path is not None else "<not found>"
    python = str(Path(sys.executable).resolve()) if str(sys.executable).strip() else "<unknown>"
    lines.append(f"  launcher: {launcher}")
    lines.append(f"  python:   {python}")
    return "\n".join(lines)


def _format_diagnostics(ctx: SetupContext) -> str:
    lines = [
        f"[bold]base dir:[/]        {ctx.base_dir}",
        f"[bold]bin dir:[/]         {ctx.bin_dir}",
        f"[bold]homebase dir:[/]    {ctx.homebase_dir}",
        f"[bold]target launcher:[/] {ctx.target}",
        f"[bold]dest launcher:[/]   {ctx.dest}",
        f"[bold]install method:[/]  {escape(ctx.install_mode)} ({escape(ctx.update_detail)})",
        "",
        f"[bold]uv:[/]    {ctx.uv_bin or '[bright_red]<missing>[/]'}",
        f"[bold]git:[/]   {ctx.git_bin or '[bright_red]<missing>[/]'}",
        f"[bold]tmux:[/]  {ctx.tmux_bin or '[bright_red]<missing>[/]'}",
        f"[bold]tmuxp:[/] {ctx.tmuxp_bin or '[bright_yellow]<missing>[/]'}",
        "",
        f"[bold]runtime ok:[/]  {ctx.runtime_ok} ({ctx.runtime_detail})",
        f"[bold]PATH ok:[/]     {ctx.in_path}",
        f"[bold]config:[/]      {ctx.config_path} exists={ctx.config_exists} valid={ctx.config_valid}",
        "",
        f"[bold]shell:[/]                {ctx.completion_shell or '[bright_yellow]<unsupported>[/]'}",
        f"[bold]completion target:[/]    {ctx.completion_target}",
        f"[bold]completion installed:[/] {ctx.completion_ok}",
        f"[bold]shell-init target:[/]    {ctx.shell_init_target}",
        f"[bold]shell-init rc:[/]        {ctx.shell_init_rc}",
        f"[bold]shell-init ok:[/]        {ctx.shell_init_ok}",
        "",
        f"[bold]tmux conf path:[/]   {ctx.tmux_conf_path}",
        f"[bold]expected binding:[/] {ctx.expected_tmux_binding}",
    ]
    if ctx.existing_tmux_binding_lines:
        lines.append("[bold]existing binding(s):[/]")
        for line in ctx.existing_tmux_binding_lines:
            lines.append(f"  {line}")
    return "\n".join(lines)


def _fix_row_label(fix: SetupFix, *, selected: bool) -> str:
    """Build the per-row label shown in the Fixes SelectionList.

    Layout: ``<action>  <tag> [<state>]  <title>``. The action column
    is the user-visible reflection of the SelectionList's selected
    state — replaces the previous [x]/[ ] checkbox glyph (which the
    user found too easy to misread)."""
    intent = fix.intent(selected=selected)
    action_word, action_color = _action_word_for_intent(intent)
    action = f"[bold {action_color}]{action_word:<{_ACTION_COL_WIDTH}}[/]"

    tag_text = (
        "required" if fix.required
        else ("recommended" if fix.recommended else "optional")
    )
    tag_color = (
        "bright_red" if fix.required
        else ("bright_yellow" if fix.recommended else "bright_cyan")
    )
    state_word, state_color = _fix_state_word(fix)
    state_chunk = f"[bold {state_color}]\\[{state_word}][/]"
    tag_chunk = f"[{tag_color}]{tag_text}[/] {state_chunk}"

    # Manual width math because Rich markup tags don't count as visible
    # chars but f-string padding does — give the label a fixed visible
    # prefix so the titles line up.
    visible_tag_width = len(tag_text) + 1 + len(state_word) + 2  # tag + " [" + word + "]"
    pad_len = max(0, _TAG_COL_WIDTH + 2 + _STATE_COL_WIDTH + 2 - visible_tag_width)
    return f"{action} {tag_chunk}{' ' * pad_len}  {fix.title}"


def _ordered_fixes(fixes: list[SetupFix]) -> list[SetupFix]:
    def _rank(fx: SetupFix) -> int:
        if fx.required:
            return 0
        if fx.recommended:
            return 1
        return 2

    return sorted(fixes, key=lambda fx: (_rank(fx),))


def _compute_intents(
    fixes: list[SetupFix], selected: set[str]
) -> dict[str, str]:
    return {fx.id: fx.intent(selected=fx.id in selected) for fx in fixes}


def _group_fixes_by_intent(
    fixes: list[SetupFix], intents: dict[str, str]
) -> dict[str, list[SetupFix]]:
    groups: dict[str, list[SetupFix]] = {
        INTENT_CREATE: [],
        INTENT_REMOVE: [],
        INTENT_KEEP: [],
        INTENT_ABSENT: [],
        INTENT_CANNOT_REMOVE: [],
        INTENT_CANNOT_CREATE: [],
    }
    for fx in fixes:
        intent = intents[fx.id]
        if intent in groups:
            groups[intent].append(fx)
    return groups


def _format_intent_section(
    label_text: str, prefix: str, suffix: str, fixes: list[SetupFix]
) -> list[str]:
    if not fixes:
        return []
    out = [f"{label_text} ({len(fixes)})[/]:"]
    for fx in fixes:
        out.append(f"  {prefix} {fx.title}{suffix}")
    return out


def _format_action_plan(fixes: list[SetupFix], selected: set[str]) -> str:
    intents = _compute_intents(fixes, selected)
    groups = _group_fixes_by_intent(fixes, intents)
    creates = groups[INTENT_CREATE]
    removes = groups[INTENT_REMOVE]
    keeps = groups[INTENT_KEEP]
    absent = groups[INTENT_ABSENT]
    cannot_remove = groups[INTENT_CANNOT_REMOVE]
    cannot_create = groups[INTENT_CANNOT_CREATE]
    lines: list[str] = []
    lines.extend(
        _format_intent_section(
            "[bold bright_green]install", "+", "", creates
        )
    )
    lines.extend(
        _format_intent_section("[bold bright_red]REMOVE", "-", "", removes)
    )
    lines.extend(
        _format_intent_section(
            "[bold bright_red]cannot install", "!", " (no installer)", cannot_create
        )
    )
    lines.extend(
        _format_intent_section(
            "[bold bright_red]cannot uninstall",
            "!",
            " (remove by hand)",
            cannot_remove,
        )
    )
    if not (creates or removes or cannot_create or cannot_remove):
        lines.append(
            "[bright_cyan]no changes — every item already matches your selection.[/]"
        )
    if keeps or absent:
        lines.append("")
        lines.append(
            f"[dim]unchanged: {len(keeps)} kept, {len(absent)} stayed absent[/]"
        )
    return "\n".join(lines)


_DEBUG_HINT_LINE = (
    "[bold]Enter[/] run   [bold]c[/] clear   [bold]y[/] copy output   "
    "[bold]↑↓[/] select"
)


def _format_debug_intro(debug_tools: list[SetupDebugTool]) -> str:
    if not debug_tools:
        return "[dim]No debug tools available.[/]"
    return _format_debug_tool_info(debug_tools[0])


def _format_debug_tool_info(tool: SetupDebugTool) -> str:
    footer = (
        "[dim]Press Enter to choose a method, then Enter to run it.[/]"
        if tool.options
        else "[dim]Press Enter to run. Output is appended below (c clears).[/]"
    )
    return "\n".join([f"[bold]{tool.label}[/]", "", tool.description, "", footer])


def _copy_to_system_clipboard(text: str) -> tuple[bool, str]:
    """Best-effort native clipboard write. Returns (ok, detail)."""
    if sys.platform == "darwin":
        cmd = ["pbcopy"]
    elif sys.platform.startswith("linux"):
        cmd = ["xclip", "-selection", "clipboard"]
    else:
        return False, f"no native clipboard for {sys.platform}"
    try:
        proc = subprocess.run(
            cmd,
            input=text,
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{cmd[0]}: {type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        return False, f"{cmd[0]} exited {proc.returncode}: {proc.stderr.strip()}"
    return True, cmd[0]


def run_setup_app(
    ctx: SetupContext,
    checks: list[SetupCheck],
    fixes: list[SetupFix],
    *,
    apply_fn: Callable[..., list[FixResult]],
    dry_run: bool = False,
    debug_tools: list[SetupDebugTool] | None = None,
    debug_activator: MainThreadActivator | None = None,
) -> ApplyOutcome | None:
    """Launch the tabbed Textual setup app.

    Returns an ``ApplyOutcome`` describing how the user ended the
    session (cancel / continue / exit), or ``None`` when Textual
    itself isn't importable. Callers MUST treat ``None`` as cancel —
    never as a signal to fall back to a legacy selector with empty
    defaults (that's how the destructive bug used to be reached)."""
    try:
        from rich.text import Text
        from textual.app import App, ComposeResult
        from textual.binding import Binding
        from textual.containers import (
            Container,
            Horizontal,
            Vertical,
            VerticalScroll,
        )
        from textual.screen import ModalScreen
        from textual.widgets import (
            Button,
            Header,
            Label,
            ListItem,
            ListView,
            RichLog,
            SelectionList,
            Static,
            TabbedContent,
            TabPane,
            Tabs,
        )
        from textual.widgets._toggle_button import ToggleButton
    except ImportError:
        return None

    # Hide the SelectionList checkbox entirely — selection state is
    # shown via the leading "keep / add / remove / skip" word in each
    # row's label instead, which the row-refresh hook updates on every
    # toggle. Empty BUTTON chars render as zero-width segments.
    ToggleButton.BUTTON_LEFT = ""
    ToggleButton.BUTTON_INNER = ""
    ToggleButton.BUTTON_RIGHT = ""

    fix_order = _ordered_fixes(fixes)
    fix_by_id = {fx.id: fx for fx in fix_order}
    debug_tool_list = list(debug_tools or [])
    debug_tool_by_id = {tool.id: tool for tool in debug_tool_list}

    class ApplyDialog(ModalScreen[ApplyOutcome]):
        """Modal log dialog shown while apply runs.

        Streams each step into a RichLog, prints a summary at the end,
        and lets the user pick "Back to setup" (return with action=
        ``continue``) or "Close & quit" (action=``exit``)."""

        BINDINGS = [
            Binding("escape", "back", "Back", show=False),
        ]

        def __init__(
            self,
            fix_list: list[SetupFix],
            selected_ids: set[str],
            dry_run_flag: bool,
        ) -> None:
            super().__init__()
            self._fix_list = fix_list
            self._selected_ids = selected_ids
            self._dry_run = dry_run_flag
            self._results: list[FixResult] = []
            self._done = False

        def compose(self) -> ComposeResult:
            with Vertical(id="dialog_box", classes="-done"):
                yield Static("Completed actions", id="dialog_title")
                yield RichLog(
                    highlight=False, markup=True, wrap=True, id="apply_log"
                )
                with Horizontal(id="dialog_buttons"):
                    # "Back to setup" is intentionally not rendered — Esc
                    # still works (see action_back). One visible button
                    # keeps the dialog uncluttered after a run finishes.
                    yield Button(
                        "Quit",
                        id="btn_apply_close",
                        variant="warning",
                        disabled=True,
                    )

        def on_mount(self) -> None:
            # Apply file-I/O operations finish in well under a second.
            # Running them synchronously on the next frame avoids the
            # worker-thread complexity that previously caused the
            # dialog to "hang" with disabled buttons.
            self.call_after_refresh(self._do_apply)

        def _emit(self, line: str) -> None:
            self.query_one("#apply_log", RichLog).write(line)

        def _do_apply(self) -> None:

            def log_fn(line: str, err: bool) -> None:
                color = "bright_red" if err else "white"
                self._emit(f"[{color}]{escape(line)}[/]")

            self._emit(
                f"[bold]Applying {len(self._selected_ids)} selected item(s)"
                + (" (dry-run)" if self._dry_run else "")
                + "…[/]"
            )
            results: list[FixResult] = []
            try:
                results = apply_fn(
                    self._fix_list,
                    self._selected_ids,
                    dry_run=self._dry_run,
                    log_fn=log_fn,
                )
            except Exception as exc:  # noqa: BLE001 - dialog-level error boundary
                import traceback

                self._emit(
                    f"[bright_red bold]apply crashed: "
                    f"{type(exc).__name__}: {escape(str(exc))}[/]"
                )
                for line in traceback.format_exc().splitlines():
                    self._emit(f"[bright_red]{escape(line)}[/]")
            self._results = results
            self._summarize()
            self._finish()

        def _summarize(self) -> None:
            log = self.query_one("#apply_log", RichLog)
            creates = [
                r for r in self._results if r.intent == INTENT_CREATE and r.success
            ]
            removes = [
                r for r in self._results if r.intent == INTENT_REMOVE and r.success
            ]
            keeps = [r for r in self._results if r.intent == INTENT_KEEP]
            failures = [r for r in self._results if not r.success]
            log.write("")
            log.write("[bold underline]Summary[/]")
            log.write(
                f"  [bright_green]installed: {len(creates)}[/]   "
                f"[bright_red]removed: {len(removes)}[/]   "
                f"[dim]kept: {len(keeps)}[/]"
            )
            if failures:
                log.write(
                    f"  [bold bright_red]failed: {len(failures)}[/]"
                )
                for r in failures:
                    log.write(
                        f"    [bright_red]- {r.title}: {r.error or '<unknown>'}[/]"
                    )
            log.write("")
            log.write(
                "[bold]Esc[/] [dim]to keep editing,[/]  "
                "[bold]Enter / Quit[/] [dim]to exit setup.[/]"
            )

        def _finish(self) -> None:
            self.query_one("#btn_apply_close", Button).disabled = False
            self.query_one("#btn_apply_close", Button).focus()
            self._done = True

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if not self._done:
                return
            if event.button.id == "btn_apply_close":
                # Tear the whole app down so the underlying screen
                # doesn't render in a transient state before exit.
                self.app.exit(
                    ApplyOutcome(action="exit", results=self._results)
                )

        def action_back(self) -> None:
            if not self._done:
                return
            self.dismiss(ApplyOutcome(action="continue", results=self._results))

    class ConfirmApplyDialog(ModalScreen[bool]):
        """Pre-apply confirmation modal. Lists what will change and
        gates the actual apply behind an explicit Enter / button press.

        Same dialog regardless of whether the apply is destructive —
        only the border colour changes (red when any REMOVE is in the
        plan, blue otherwise). The "Apply changes" button is focused
        by default so Enter triggers it directly."""

        BINDINGS = [
            Binding("escape", "cancel", "Cancel", show=False),
        ]

        def __init__(
            self,
            creates: list[str],
            removes: list[str],
        ) -> None:
            super().__init__()
            self._creates = creates
            self._removes = removes
            self._destructive = bool(removes)

        def compose(self) -> ComposeResult:
            border_class = "-confirm-destructive" if self._destructive else "-confirm"
            with Vertical(id="dialog_box", classes=border_class):
                title = (
                    "Confirm destructive apply"
                    if self._destructive
                    else "Confirm apply"
                )
                title_color = "bright_red" if self._destructive else "bright_cyan"
                yield Static(
                    f"[bold {title_color}]{title}[/]",
                    id="dialog_title",
                )
                lines: list[str] = []
                if self._removes:
                    lines.append(
                        f"[bold bright_red]REMOVE {len(self._removes)} "
                        "item(s) from your system:[/]"
                    )
                    for title in self._removes:
                        lines.append(f"  [bright_red]- {title}[/]")
                    if self._creates:
                        lines.append("")
                if self._creates:
                    lines.append(
                        f"[bold bright_green]INSTALL {len(self._creates)} "
                        "item(s):[/]"
                    )
                    for title in self._creates:
                        lines.append(f"  [bright_green]+ {title}[/]")
                lines.append("")
                lines.append(
                    "[bold]Press Enter to apply, Esc to cancel.[/]"
                )
                yield Static(
                    Text.from_markup("\n".join(lines)),
                    id="apply_log",
                )
                with Horizontal(id="dialog_buttons"):
                    yield Button("Cancel (Esc)", id="btn_confirm_cancel")
                    yield Button(
                        "Apply changes",
                        id="btn_confirm_ok",
                        variant="error" if self._destructive else "success",
                    )

        def on_mount(self) -> None:
            # Default focus on Apply changes so Enter triggers it —
            # explicit user request. Esc still cancels.
            self.query_one("#btn_confirm_ok", Button).focus()

        def on_button_pressed(self, event: Button.Pressed) -> None:
            bid = event.button.id
            if bid == "btn_confirm_ok":
                self.dismiss(True)
            elif bid == "btn_confirm_cancel":
                self.dismiss(False)

        def action_cancel(self) -> None:
            self.dismiss(False)

    class _SetupApp(App[ApplyOutcome | None]):
        TITLE = "Homebase Setup"
        CSS = """
        Screen { align: center middle; }

        TabbedContent { height: 1fr; }

        /* --- SelectionList checkbox glyphs ----------------------- */
        SelectionList {
            height: 1fr;
            text-wrap: nowrap;
            text-overflow: ellipsis;
            border: round $panel;
            padding: 0 1;
        }
        SelectionList > .selection-list--button {
            color: $panel;
            background: $panel;
        }
        SelectionList > .selection-list--button-highlighted {
            color: $primary;
            background: $primary;
        }
        SelectionList > .selection-list--button-selected {
            color: $success;
            background: $panel;
            text-style: bold;
        }
        SelectionList > .selection-list--button-selected-highlighted {
            color: $success-lighten-2;
            background: $primary;
            text-style: bold;
        }

        /* --- Fixes tab (asymmetric "cross" grid) ----------------- */
        /* Row-span layout: the inner horizontal divider on the left
         * column sits ABOVE the one on the right column, so SL is
         * shortest, fix details is tallest, plan is mid-tall, apply
         * controls is shortest. */
        #fixes_grid {
            layout: grid;
            grid-size: 2 3;
            grid-columns: 3fr 2fr;
            grid-rows: 2fr 1fr 1fr;
            grid-gutter: 1 1;
            padding: 1 1 0 1;
        }
        #fix_right {
            row-span: 2;
            border: round $panel;
            padding: 0 1;
        }
        #plan_box {
            row-span: 2;
            border: round $accent;
            padding: 0 1;
        }
        #detail_title { text-style: bold; padding: 0 0 1 0; }
        #detail_block { padding: 0 0 1 0; }
        #preview_title { text-style: bold; padding: 1 0 0 0; }
        #preview_block { padding: 0 0 1 0; color: $text-muted; }
        .pane_text { padding: 1 2; }
        #plan_title { text-style: bold; padding: 0 0 1 0; }
        #plan_block { padding: 0; height: auto; }

        /* apply controls cell (bottom-right, smallest)
         * Single horizontal row of three Buttons: Apply prominent
         * (success variant + wider) plus the two secondary actions.
         * Letting Button keep its natural 3-line height keeps the
         * label vertically centered. */
        #apply_controls {
            layout: horizontal;
            align: center middle;
        }
        #btn_apply {
            width: 2fr;
            margin: 0 1 0 0;
        }
        #btn_all, #btn_none {
            width: 1fr;
            margin: 0 1 0 0;
        }

        /* --- Self-update tab ------------------------------------- */
        #self_update_body { padding: 1 2; }
        #self_update_info { height: auto; padding: 0 0 1 0; }
        #btn_run_update { margin: 0 0 1 0; min-width: 30; }
        #self_update_log {
            height: 1fr;
            border: round $accent;
            background: $surface;
        }

        /* --- Debug tab (left menu | info+config / output / hints) - */
        #debug_body { height: 1fr; padding: 1 1 0 1; }
        #debug_menu {
            width: 34;
            height: 1fr;
            border: round $panel;
            margin: 0 1 0 0;
        }
        #debug_menu > ListItem { padding: 0 1; }
        #debug_right { width: 1fr; height: 1fr; }
        #debug_info {
            height: auto;
            max-height: 45%;
            border: round $accent;
            padding: 0 1;
            margin: 0 0 1 0;
        }
        #debug_options {
            height: auto;
            max-height: 40%;
            border: round $warning;
            margin: 0 0 1 0;
        }
        #debug_options > ListItem { padding: 0 1; }
        #debug_log {
            height: 1fr;
            border: round $accent;
            background: $surface;
        }
        #debug_hint { height: 1; color: $text-muted; padding: 0 1; }

        /* --- bottom cancel bar (overview only) -------------------
         * action_bar height matches the natural Button height (3)
         * so the label sits vertically centered. margin-bottom keeps
         * the bar away from the screen edge without affecting the
         * label position the way bottom padding did. */
        #action_bar {
            dock: bottom;
            height: 3;
            margin: 0 2 2 2;
        }
        #btn_cancel { width: 100%; }

        /* --- Modal dialogs (Confirm + Completed actions) ---------
         * Same structural CSS for both; the border colour is the
         * only thing that varies, set via classes on #dialog_box. */
        ApplyDialog, ConfirmApplyDialog {
            align: center middle;
        }
        #dialog_box {
            width: 80%;
            height: 70%;
            background: $boost;
            padding: 1 2;
        }
        #dialog_box.-done { border: round $success; }
        #dialog_box.-confirm { border: round $accent; }
        #dialog_box.-confirm-destructive { border: round $error; }
        #dialog_title {
            text-style: bold;
            padding: 0 0 1 0;
        }
        #apply_log {
            height: 1fr;
            border: round $panel;
            background: $surface;
            padding: 0 1;
            margin: 0 0 1 0;
        }
        #dialog_buttons { height: 3; align-horizontal: right; }
        #dialog_buttons Button { margin: 0 0 0 1; min-width: 18; }
        """
        TAB_ORDER = ("overview", "fixes", "self_update", "diagnostics", "debug")
        BINDINGS = [
            Binding("ctrl+s", "apply", "Apply"),
            Binding("q", "cancel", "Cancel"),
            Binding("escape", "cancel", "Cancel", show=False),
            # Override Textual's default ctrl+q → app.quit (which
            # returns None and used to fall through to the legacy
            # selector with empty defaults — the destructive bug).
            Binding("ctrl+q", "cancel", "Cancel", show=False),
            # Same story for ctrl+c.
            Binding("ctrl+c", "cancel", "Cancel", show=False),
            # `a` and `n` were the wipe-everything footguns. Replaced
            # with Ctrl-modified chords so a stray keystroke can't
            # deselect every fix (which would otherwise trigger a
            # REMOVE for each currently-installed item on apply).
            Binding("ctrl+a", "all", "Select all"),
            Binding("ctrl+n", "none", "Select none"),
            Binding("u", "run_self_update", "Run update"),
            Binding("c", "debug_clear", "Clear", show=False),
            Binding("y", "debug_copy", "Copy", show=False),
            Binding("left", "prev_tab", "Prev tab"),
            Binding("right", "next_tab", "Next tab"),
            Binding("1", "show_tab('overview')", "Overview", show=False),
            Binding("2", "show_tab('fixes')", "Fixes", show=False),
            Binding("3", "show_tab('self_update')", "Self-update", show=False),
            Binding("4", "show_tab('diagnostics')", "Diagnostics", show=False),
            Binding("5", "show_tab('debug')", "Debug", show=False),
        ]

        def __init__(self) -> None:
            super().__init__()
            self._update_proc: subprocess.Popen[str] | None = None
            self._update_thread: threading.Thread | None = None
            self._debug_thread: threading.Thread | None = None
            self._debug_detail_thread: threading.Thread | None = None
            self._debug_selected_id: str | None = (
                debug_tool_list[0].id if debug_tool_list else None
            )
            self._debug_options_tool_id: str | None = None
            self._debug_last_report: str = ""

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            with TabbedContent(initial="fixes"):
                with TabPane("Overview [1]", id="overview"):
                    with VerticalScroll():
                        yield Static(
                            Text.from_markup(_format_overview(checks)),
                            classes="pane_text",
                        )
                with TabPane("Fixes [2]", id="fixes"):
                    with Container(id="fixes_grid"):
                        rows = [
                            (
                                Text.from_markup(
                                    _fix_row_label(fx, selected=fx.selected_default)
                                ),
                                fx.id,
                                fx.selected_default,
                            )
                            for fx in fix_order
                        ]
                        # row-major placement with row-span on
                        # fix_right and plan_box gives the desired
                        # asymmetric "cross" layout (see CSS comment).
                        yield SelectionList[str](*rows, id="fixes_list")
                        with VerticalScroll(id="fix_right"):
                            yield Static("Fix details", id="detail_title")
                            yield Static("", id="detail_block")
                            yield Static("Preview", id="preview_title")
                            yield Static("", id="preview_block")
                        with VerticalScroll(id="plan_box"):
                            yield Static("Apply plan", id="plan_title")
                            yield Static("", id="plan_block")
                        with Horizontal(id="apply_controls"):
                            yield Button(
                                "Apply (Ctrl+S)",
                                id="btn_apply",
                                variant="success",
                            )
                            yield Button("Select all (Ctrl+A)", id="btn_all")
                            yield Button("Select none (Ctrl+N)", id="btn_none")
                with TabPane("Self-update [3]", id="self_update"):
                    with Vertical(id="self_update_body"):
                        yield Static(
                            Text.from_markup(_format_self_update_static(ctx)),
                            id="self_update_info",
                        )
                        yield Button(
                            "Run update (u)" if ctx.update_cmd else "Run update — unavailable",
                            id="btn_run_update",
                            variant="success" if ctx.update_cmd else "default",
                            disabled=not ctx.update_cmd,
                        )
                        yield RichLog(
                            highlight=True,
                            markup=True,
                            wrap=True,
                            id="self_update_log",
                        )
                with TabPane("Diagnostics [4]", id="diagnostics"):
                    with VerticalScroll():
                        yield Static(
                            Text.from_markup(_format_diagnostics(ctx)),
                            classes="pane_text",
                        )
                with TabPane("Debug [5]", id="debug"):
                    with Horizontal(id="debug_body"):
                        yield ListView(
                            *[
                                ListItem(
                                    Label(tool.label),
                                    id=f"debug_item_{tool.id}",
                                )
                                for tool in debug_tool_list
                            ],
                            id="debug_menu",
                        )
                        with Vertical(id="debug_right"):
                            yield Static(
                                Text.from_markup(
                                    _format_debug_intro(debug_tool_list)
                                ),
                                id="debug_info",
                            )
                            yield ListView(id="debug_options")
                            yield RichLog(
                                highlight=False,
                                markup=True,
                                wrap=True,
                                id="debug_log",
                            )
                            yield Static(
                                Text.from_markup(_DEBUG_HINT_LINE),
                                id="debug_hint",
                            )
            with Horizontal(id="action_bar"):
                yield Button(
                    "Cancel & Quit (q)", id="btn_cancel", variant="warning"
                )

        # --- lifecycle ----------------------------------------------

        def on_mount(self) -> None:
            # Let worker-thread debug tools marshal the macOS activation
            # onto this (main) thread — the same context as live `b`.
            if debug_activator is not None:
                debug_activator.call = self.call_from_thread
            self._sync_focus_to_active_tab()
            self._refresh_detail()
            self._refresh_action_bar()

        def on_unmount(self) -> None:
            if debug_activator is not None:
                debug_activator.call = None

        def on_tabbed_content_tab_activated(self, event) -> None:
            self._sync_focus_to_active_tab(event.pane.id)
            self._refresh_detail()
            self._refresh_action_bar(event.pane.id)
            if event.pane.id == "debug" and self._debug_selected_id is not None:
                tool = debug_tool_by_id.get(self._debug_selected_id)
                if tool is not None:
                    # Now that the tab is active, run the (possibly slow)
                    # live detail probe and (re)build the method list.
                    self._refresh_debug_info(tool)
                    self._populate_debug_options(tool)

        def on_selection_list_selection_highlighted(self, _event) -> None:
            self._refresh_detail()

        def on_selection_list_selection_toggled(self, _event) -> None:
            self._refresh_detail()
            self._refresh_action_bar()
            self._refresh_row_labels()

        def on_selection_list_selected_changed(self, _event) -> None:
            # Catches programmatic changes too (Select all / Select
            # none, restored state on tab activation, etc.).
            self._refresh_row_labels()
            self._refresh_action_bar()

        def on_list_view_highlighted(self, event) -> None:
            list_id = getattr(event.list_view, "id", None)
            if list_id != "debug_menu":
                return
            tool = self._tool_for_item(event.item)
            if tool is None:
                return
            self._debug_selected_id = tool.id
            self._refresh_debug_info(tool)
            self._populate_debug_options(tool)

        def on_list_view_selected(self, event) -> None:
            list_id = getattr(event.list_view, "id", None)
            if list_id == "debug_menu":
                tool = self._tool_for_item(event.item)
                if tool is None:
                    return
                self._debug_selected_id = tool.id
                if tool.options:
                    # Drill into the method list rather than running.
                    self._focus_debug_options()
                elif tool.run is not None:
                    self._run_debug_report(tool.label, tool.run)
                return
            if list_id == "debug_options":
                option = self._option_for_item(event.item)
                if option is not None:
                    self._run_debug_report(option.label, option.run)

        @staticmethod
        def _tool_for_item(item) -> "SetupDebugTool | None":
            item_id = getattr(item, "id", None)
            if not item_id or not item_id.startswith("debug_item_"):
                return None
            return debug_tool_by_id.get(item_id[len("debug_item_") :])

        def _option_for_item(self, item) -> "SetupDebugOption | None":
            item_id = getattr(item, "id", None)
            if not item_id or not item_id.startswith("debug_opt_"):
                return None
            tool = debug_tool_by_id.get(self._debug_options_tool_id or "")
            if tool is None:
                return None
            opt_id = item_id[len("debug_opt_") :]
            return next((o for o in tool.options if o.id == opt_id), None)

        def _populate_debug_options(self, tool: "SetupDebugTool") -> None:
            from textual.css.query import NoMatches

            try:
                options = self.query_one("#debug_options", ListView)
            except NoMatches:
                return
            if self._debug_options_tool_id == tool.id:
                return
            self._debug_options_tool_id = tool.id
            options.clear()
            options.display = bool(tool.options)
            for opt in tool.options:
                options.append(
                    ListItem(Label(opt.label), id=f"debug_opt_{opt.id}")
                )

        def _focus_debug_options(self) -> None:
            from textual.css.query import NoMatches

            try:
                options = self.query_one("#debug_options", ListView)
            except NoMatches:
                return
            if not options.display:
                return
            if options.index is None:
                options.index = 0
            options.focus()

        def _refresh_debug_info(self, tool: "SetupDebugTool") -> None:
            from textual.css.query import NoMatches

            try:
                info = self.query_one("#debug_info", Static)
            except NoMatches:
                return
            info.update(Text.from_markup(_format_debug_tool_info(tool)))
            if tool.detail is not None and self._active_tab_id() == "debug":
                self._start_debug_detail(tool)

        def _start_debug_detail(self, tool: "SetupDebugTool") -> None:
            if (
                self._debug_detail_thread is not None
                and self._debug_detail_thread.is_alive()
            ):
                return
            detail_fn = tool.detail
            if detail_fn is None:
                return
            tool_id = tool.id

            def _work() -> None:
                try:
                    text = detail_fn()
                except Exception as exc:  # noqa: BLE001 - surface any probe crash inline
                    text = f"[bright_red]detail probe failed: {escape(str(exc))}[/]"
                self.call_from_thread(self._apply_debug_detail, tool_id, text)

            t = threading.Thread(target=_work, daemon=True)
            self._debug_detail_thread = t
            t.start()

        def _apply_debug_detail(self, tool_id: str, detail_text: str) -> None:
            from textual.css.query import NoMatches

            if self._debug_selected_id != tool_id:
                return
            tool = debug_tool_by_id.get(tool_id)
            if tool is None:
                return
            try:
                info = self.query_one("#debug_info", Static)
            except NoMatches:
                return
            body = _format_debug_tool_info(tool) + "\n\n" + detail_text
            info.update(Text.from_markup(body))

        def _refresh_row_labels(self) -> None:
            """Update the action word at the start of every Fix row so
            it always reflects the current selection state."""
            from textual.css.query import NoMatches

            try:
                sl = self.query_one("#fixes_list", SelectionList)
            except NoMatches:
                return
            selected = self._selected_set()
            for idx, fx in enumerate(fix_order):
                label = _fix_row_label(fx, selected=fx.id in selected)
                sl.replace_option_prompt_at_index(idx, Text.from_markup(label))

        def on_button_pressed(self, event: "Button.Pressed") -> None:
            bid = event.button.id
            if bid == "btn_apply":
                self.action_apply()
            elif bid == "btn_cancel":
                self.action_cancel()
            elif bid == "btn_all":
                self.action_all()
            elif bid == "btn_none":
                self.action_none()
            elif bid == "btn_run_update":
                self.action_run_self_update()

        # --- bindings ----------------------------------------------

        def check_action(self, action: str, parameters):
            _ = parameters
            active = self._active_tab_id()
            if action in ("all", "none", "apply"):
                return active == "fixes"
            if action == "run_self_update":
                return active == "self_update"
            if action in ("debug_clear", "debug_copy"):
                return active == "debug"
            return True

        # --- helpers -----------------------------------------------

        def _active_tab_id(self) -> str | None:
            from textual.css.query import NoMatches

            try:
                return self.query_one(TabbedContent).active
            except NoMatches:
                return None

        def _selected_set(self) -> set[str]:
            from textual.css.query import NoMatches

            try:
                widget = self.query_one("#fixes_list", SelectionList)
            except NoMatches:
                return set()
            return {str(v) for v in widget.selected}

        def _sync_focus_to_active_tab(self, active_id: str | None = None) -> None:
            from textual.css.query import NoMatches

            if active_id is None:
                active_id = self._active_tab_id()
            try:
                if active_id == "fixes":
                    self.query_one("#fixes_list", SelectionList).focus()
                elif active_id == "debug" and debug_tool_list:
                    self.query_one("#debug_menu", ListView).focus()
                else:
                    self.query_one(Tabs).focus()
            except NoMatches:
                pass

        def _refresh_action_bar(self, active_id: str | None = None) -> None:
            from textual.css.query import NoMatches

            if active_id is None:
                active_id = self._active_tab_id()
            on_overview = active_id == "overview"

            selected = self._selected_set()
            intents = _compute_intents(fix_order, selected)
            create_count = sum(1 for i in intents.values() if i == INTENT_CREATE)
            remove_count = sum(1 for i in intents.values() if i == INTENT_REMOVE)
            cannot_count = sum(
                1
                for i in intents.values()
                if i in {INTENT_CANNOT_CREATE, INTENT_CANNOT_REMOVE}
            )
            total_changes = create_count + remove_count

            try:
                apply_btn = self.query_one("#btn_apply", Button)
                if total_changes == 0 and cannot_count == 0:
                    apply_btn.label = "Apply (no changes)"
                    apply_btn.disabled = True
                else:
                    pieces: list[str] = []
                    if create_count:
                        pieces.append(f"+{create_count}")
                    if remove_count:
                        pieces.append(f"-{remove_count}")
                    if cannot_count:
                        pieces.append(f"!{cannot_count}")
                    apply_btn.label = "Apply " + " ".join(pieces) + "  (Ctrl+S)"
                    apply_btn.disabled = False
                self.query_one("#plan_block", Static).update(
                    Text.from_markup(_format_action_plan(fix_order, selected))
                )
            except NoMatches:
                pass
            try:
                self.query_one("#action_bar", Horizontal).display = on_overview
            except NoMatches:
                pass

        def _refresh_detail(self) -> None:
            from textual.css.query import NoMatches
            from textual.widgets.option_list import OptionDoesNotExist

            try:
                widget = self.query_one("#fixes_list", SelectionList)
            except NoMatches:
                return
            current = widget.highlighted
            detail = self.query_one("#detail_block", Static)
            preview = self.query_one("#preview_block", Static)
            if current is None:
                detail.update("No fix highlighted.")
                preview.update("")
                return
            try:
                value = widget.get_option_at_index(current).value
            except OptionDoesNotExist:
                detail.update("No fix highlighted.")
                preview.update("")
                return
            selected_id = str(value)
            fix = fix_by_id.get(selected_id)
            if fix is None:
                detail.update("No fix highlighted.")
                preview.update("")
                return
            currently_selected = selected_id in self._selected_set()
            intent = fix.intent(selected=currently_selected)
            tag_text = (
                "required" if fix.required
                else ("recommended" if fix.recommended else "optional")
            )
            tag_color = (
                "bright_red" if fix.required
                else ("bright_yellow" if fix.recommended else "bright_cyan")
            )
            lines = [
                f"[bold]What:[/]    {fix.title}",
                f"[bold]Type:[/]    [{tag_color}]{tag_text}[/]",
                f"[bold]State:[/]   {_fix_state_text(fix)}",
                f"[bold]Current:[/] {fix.current_state_text or '<unknown>'}",
                "",
                f"[bold]On apply:[/] {_intent_label(intent)}",
            ]
            if intent == INTENT_REMOVE:
                lines.append(
                    "  [bright_red]This will REMOVE the item from your system.[/]"
                )
            if intent == INTENT_CANNOT_REMOVE:
                lines.append(
                    "  [bright_red]Setup cannot uninstall this. Remove it by hand if you really want to.[/]"
                )
            if intent == INTENT_CANNOT_CREATE:
                lines.append(
                    "  [bright_red]No installer wired up for this item.[/]"
                )
            if intent == INTENT_KEEP:
                lines.append("  [dim]Already configured. Leaving it as-is.[/]")
            if intent == INTENT_ABSENT:
                lines.append(
                    "  [dim]Not installed and not selected. No-op.[/]"
                )
            if intent == INTENT_CREATE:
                lines.append(
                    "  [bright_green]Will install/configure this item.[/]"
                )
            if fix.requires:
                lines.append("")
                lines.append(f"[bold]Depends on:[/] {', '.join(fix.requires)}")
            if fix.description:
                lines.append("")
                lines.append(fix.description)
            detail.update(Text.from_markup("\n".join(lines)))

            pane_title, pane_body = _right_pane_for_intent(fix, intent)
            self.query_one("#preview_title", Static).update(pane_title)
            preview.update(Text.from_markup(pane_body))

        # --- actions ----------------------------------------------

        def action_apply(self) -> None:
            widget = self.query_one("#fixes_list", SelectionList)
            selected = {str(value) for value in widget.selected}
            intents = _compute_intents(fix_order, selected)
            create_ids = [
                fid for fid, i in intents.items() if i == INTENT_CREATE
            ]
            remove_ids = [
                fid for fid, i in intents.items() if i == INTENT_REMOVE
            ]
            if not create_ids and not remove_ids:
                return  # nothing to apply

            # Safety net: refuse to apply if it would remove every
            # currently-installed item at once. That's never a valid
            # outcome of normal use; it's the destructive bug pattern
            # that wiped a user's config.
            installed = [fx for fx in fix_order if fx.currently_present]
            if installed and len(remove_ids) == len(installed):
                self.notify(
                    f"Refusing to apply: this would REMOVE every "
                    f"installed item ({len(remove_ids)}). Re-check "
                    f"your selections (Ctrl+A to select all, then "
                    f"un-check only what you want to remove).",
                    title="Setup blocked",
                    severity="error",
                    timeout=12,
                )
                return

            def _proceed() -> None:
                def _on_dismiss(outcome: ApplyOutcome | None) -> None:
                    self.exit(outcome or ApplyOutcome(action="continue"))

                self.push_screen(
                    ApplyDialog(fix_order, selected, dry_run),
                    _on_dismiss,
                )

            # Always show the confirmation dialog so the user gets to
            # see the plan and explicitly approve via Enter / Apply
            # changes. Destructive plans use a red border + variant;
            # creates-only use a blue border + green button.
            def _on_confirm(confirmed: bool | None) -> None:
                if confirmed:
                    _proceed()

            creates = [fix_by_id[fid].title for fid in create_ids]
            removes = [fix_by_id[fid].title for fid in remove_ids]
            self.push_screen(
                ConfirmApplyDialog(creates, removes),
                _on_confirm,
            )

        def action_cancel(self) -> None:
            self.exit(ApplyOutcome(action="cancel"))

        def action_all(self) -> None:
            self.query_one("#fixes_list", SelectionList).select_all()
            self._refresh_action_bar()

        def action_none(self) -> None:
            self.query_one("#fixes_list", SelectionList).deselect_all()
            self._refresh_action_bar()

        def action_show_tab(self, tab_id: str) -> None:
            self.query_one(TabbedContent).active = tab_id

        def action_prev_tab(self) -> None:
            self._cycle_tab(-1)

        def action_next_tab(self) -> None:
            self._cycle_tab(+1)

        def _cycle_tab(self, step: int) -> None:
            tabs = self.query_one(TabbedContent)
            order = self.TAB_ORDER
            try:
                idx = order.index(tabs.active)
            except ValueError:
                idx = 0
            new_idx = max(0, min(len(order) - 1, idx + step))
            tabs.active = order[new_idx]

        # --- self-update ----------------------------------------

        def action_run_self_update(self) -> None:
            if not ctx.update_cmd:
                return
            if self._update_proc is not None and self._update_proc.poll() is None:
                return
            log = self.query_one("#self_update_log", RichLog)
            log.write(f"[bold]$ {ctx.update_cmd}[/]")
            try:
                proc = subprocess.Popen(  # noqa: S603 - command comes from ctx
                    shlex.split(ctx.update_cmd),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except (OSError, ValueError) as exc:
                log.write(f"[bright_red]launch failed: {exc}[/]")
                return
            self._update_proc = proc
            button = self.query_one("#btn_run_update", Button)
            button.label = "Running…"
            button.disabled = True

            def _pump() -> None:
                assert proc.stdout is not None
                for line in proc.stdout:
                    self.call_from_thread(log.write, line.rstrip())
                rc = proc.wait()
                if rc == 0:
                    self.call_from_thread(
                        log.write, "[bold bright_green]update succeeded[/]"
                    )
                else:
                    self.call_from_thread(
                        log.write,
                        f"[bold bright_red]update failed (exit {rc})[/]",
                    )
                self.call_from_thread(self._finish_update)

            t = threading.Thread(target=_pump, daemon=True)
            self._update_thread = t
            t.start()

        def _finish_update(self) -> None:
            button = self.query_one("#btn_run_update", Button)
            button.label = "Run update (u)" if ctx.update_cmd else "Run update — unavailable"
            button.disabled = not ctx.update_cmd

        # --- debug tools ----------------------------------------

        def action_debug_clear(self) -> None:
            from textual.css.query import NoMatches

            try:
                self.query_one("#debug_log", RichLog).clear()
            except NoMatches:
                return
            self._debug_last_report = ""

        def action_debug_copy(self) -> None:
            if not self._debug_last_report:
                self.notify("Nothing to copy yet.", severity="warning", timeout=4)
                return
            # Terminal OSC52 path (works over SSH / supported terminals).
            self.copy_to_clipboard(self._debug_last_report)
            # Native clipboard fallback; OSC52 is silently dropped by many
            # terminals, so on macOS also push straight to pbcopy.
            sys_ok, sys_detail = _copy_to_system_clipboard(self._debug_last_report)
            if sys_ok:
                self.notify("Output copied to clipboard.", timeout=4)
            else:
                self.notify(
                    f"Sent to terminal clipboard (OSC52). Native copy: {sys_detail}",
                    timeout=6,
                )

        def _run_debug_report(
            self, label: str, run_fn: "Callable[[], str]"
        ) -> None:
            if self._debug_thread is not None and self._debug_thread.is_alive():
                return
            log = self.query_one("#debug_log", RichLog)
            # The log is never auto-cleared — runs accumulate so earlier
            # output stays visible. Only `c` clears it.
            log.write("[dim]" + "─" * 48 + "[/]")
            log.write(f"[bold]running: {label}…[/]")
            self._set_debug_running(True)

            def _work() -> None:
                try:
                    report = run_fn()
                except Exception as exc:  # noqa: BLE001 - surface any tool crash in the log
                    import traceback

                    tb = traceback.format_exc()
                    self._debug_last_report = (
                        f"debug tool crashed: {type(exc).__name__}: {exc}\n{tb}"
                    )
                    self.call_from_thread(
                        log.write,
                        f"[bright_red bold]debug tool crashed: "
                        f"{type(exc).__name__}: {escape(str(exc))}[/]",
                    )
                    for line in tb.splitlines():
                        self.call_from_thread(log.write, f"[bright_red]{escape(line)}[/]")
                else:
                    self._debug_last_report = Text.from_markup(report).plain
                    self.call_from_thread(log.write, report)
                self.call_from_thread(self._set_debug_running, False)

            t = threading.Thread(target=_work, daemon=True)
            self._debug_thread = t
            t.start()

        def _set_debug_running(self, running: bool) -> None:
            from textual.css.query import NoMatches

            try:
                menu = self.query_one("#debug_menu", ListView)
            except NoMatches:
                return
            menu.disabled = running
            try:
                options = self.query_one("#debug_options", ListView)
            except NoMatches:
                options = None
            if options is not None:
                options.disabled = running
            if not running:
                # Return focus to wherever the run was launched from so the
                # user can immediately pick another method or tool.
                if options is not None and options.display:
                    options.focus()
                else:
                    menu.focus()

    app = _SetupApp()
    return app.run()


__all__ = ["run_setup_app"]
