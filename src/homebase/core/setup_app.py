from __future__ import annotations

import shlex
import subprocess
import sys
import threading
from pathlib import Path

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
    SetupCheck,
    SetupContext,
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


def _fix_state_marker(fix: SetupFix) -> str:
    """Marker shown for a fix item indicating its current state."""
    if fix.currently_correct:
        return "[bold bright_green]●[/]"  # configured
    if fix.currently_present:
        return "[bold bright_yellow]●[/]"  # present but stale/wrong
    if fix.required:
        return "[bold bright_red]●[/]"  # missing required
    if fix.recommended:
        return "[bold bright_yellow]○[/]"  # missing recommended
    return "[bold bright_cyan]○[/]"  # missing optional


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
    lines: list[str] = []
    if ctx.update_cmd:
        lines.append("[bold bright_green]Self-update available[/]")
        lines.append(f"  command: [bold]{ctx.update_cmd}[/]")
        lines.append(f"  detail:  {ctx.update_detail}")
    else:
        lines.append("[bold bright_yellow]Self-update needs manual action[/]")
        lines.append(f"  detail:  {ctx.update_detail or '<unknown>'}")
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


def _fix_row_label(fix: SetupFix) -> str:
    marker = _fix_state_marker(fix)
    tag_color = "bright_red" if fix.required else (
        "bright_yellow" if fix.recommended else "bright_cyan"
    )
    tag_text = "required" if fix.required else ("recommended" if fix.recommended else "optional")
    tag = f"[{tag_color}]{tag_text:>11}[/]"
    return f"{marker} {tag}  {fix.title}"


def _ordered_fixes(fixes: list[SetupFix]) -> list[SetupFix]:
    """Required first, then recommended, then optional."""
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


def _format_action_plan(fixes: list[SetupFix], selected: set[str]) -> str:
    intents = _compute_intents(fixes, selected)
    creates = [fx for fx in fixes if intents[fx.id] == INTENT_CREATE]
    removes = [fx for fx in fixes if intents[fx.id] == INTENT_REMOVE]
    keeps = [fx for fx in fixes if intents[fx.id] == INTENT_KEEP]
    absent = [fx for fx in fixes if intents[fx.id] == INTENT_ABSENT]
    cannot_remove = [fx for fx in fixes if intents[fx.id] == INTENT_CANNOT_REMOVE]
    cannot_create = [fx for fx in fixes if intents[fx.id] == INTENT_CANNOT_CREATE]
    lines: list[str] = []
    if creates:
        lines.append(f"[bold bright_green]install ({len(creates)})[/]:")
        for fx in creates:
            lines.append(f"  + {fx.title}")
    if removes:
        lines.append(f"[bold bright_red]REMOVE ({len(removes)})[/]:")
        for fx in removes:
            lines.append(f"  - {fx.title}")
    if cannot_create:
        lines.append(f"[bold bright_red]cannot install ({len(cannot_create)})[/]:")
        for fx in cannot_create:
            lines.append(f"  ! {fx.title} (no installer)")
    if cannot_remove:
        lines.append(f"[bold bright_red]cannot uninstall ({len(cannot_remove)})[/]:")
        for fx in cannot_remove:
            lines.append(f"  ! {fx.title} (remove by hand)")
    if not creates and not removes and not cannot_create and not cannot_remove:
        lines.append("[bright_cyan]no changes — every item already matches your selection.[/]")
    if keeps or absent:
        lines.append("")
        lines.append(
            f"[dim]unchanged: {len(keeps)} kept, {len(absent)} stayed absent[/]"
        )
    return "\n".join(lines)


def run_setup_app(
    ctx: SetupContext,
    checks: list[SetupCheck],
    fixes: list[SetupFix],
) -> set[str] | None:
    """Launch the tabbed Textual setup app.

    Returns the set of selected fix ids the user wants present after
    apply, or None on cancel. Selected = present (keep or install);
    unselected = absent (skip or remove).
    """
    try:
        from rich.text import Text
        from textual.app import App, ComposeResult
        from textual.binding import Binding
        from textual.containers import Horizontal, Vertical
        from textual.widgets import (
            Header,
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

    # Render the SelectionList checkbox as "[x]" / "[ ]". CSS below
    # makes the inner color match the row background when unselected,
    # so it visually reads as "[ ]" in that case.
    ToggleButton.BUTTON_LEFT = "["
    ToggleButton.BUTTON_INNER = "x"
    ToggleButton.BUTTON_RIGHT = "]"

    fix_order = _ordered_fixes(fixes)
    fix_by_id = {fx.id: fx for fx in fix_order}
    total_fixes = len(fix_order)

    class _SetupApp(App[set[str] | None]):
        TITLE = "Homebase Setup"
        CSS = """
        Screen { align: center middle; }
        #panel { width: 100%; height: 100%; }
        TabbedContent { height: 1fr; }

        SelectionList {
            height: 1fr;
            text-wrap: nowrap;
            text-overflow: ellipsis;
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

        #fixes_grid { height: 1fr; }
        #fix_body { height: 2fr; }
        #fixes_bottom { height: 1fr; max-height: 24; min-height: 12; }
        #fix_left { width: 6fr; border: round $panel; }
        #fix_right { width: 5fr; border: round $panel; padding: 0 1; }
        #detail_title { text-style: bold; padding: 0 0 1 0; }
        #detail_block { padding: 0 0 1 0; }
        #preview_title { text-style: bold; padding: 1 0 0 0; }
        #preview_block { padding: 0 0 1 0; color: $text-muted; }
        .pane_text { padding: 1 2; }

        #apply_controls { width: 6fr; padding: 0 1; }
        #btn_apply_fixes {
            height: 3fr;
            border: round $success;
            background: $success-darken-2;
            color: $text;
            text-style: bold;
            content-align: center middle;
            margin: 0 0 1 0;
        }
        #btn_apply_fixes.-disabled {
            background: $surface-darken-2;
            color: $text-muted;
            border: round $surface;
            text-style: none;
        }
        #apply_secondary { height: 1fr; }
        #apply_secondary Static {
            background: $surface;
            color: $text-muted;
            border: round $surface-lighten-1;
            content-align: center middle;
            margin: 0 1 0 0;
            height: 1fr;
        }

        #plan_box {
            width: 5fr;
            border: round $accent;
            padding: 0 1;
        }
        #plan_title { text-style: bold; padding: 0 0 1 0; }
        #plan_block { padding: 0; }

        #self_update_body { height: 1fr; padding: 1 2; }
        #self_update_info { height: auto; padding: 0 0 1 0; }
        #self_update_button {
            background: $success-darken-2;
            color: $text;
            text-style: bold;
            content-align: center middle;
            width: 40;
            height: 5;
            border: round $success;
            margin: 1 0;
        }
        #self_update_button.-disabled {
            background: $surface-darken-1;
            color: $text-muted;
            border: round $surface;
            text-style: none;
        }
        #self_update_log {
            height: 1fr;
            border: round $accent;
            background: $surface;
        }

        #action_bar {
            dock: bottom;
            height: 5;
            padding: 1 2 2 2;
        }
        #action_bar Static { padding: 1 2; content-align: center middle; }
        #btn_cancel {
            background: $warning-darken-2;
            color: $text;
            min-width: 14;
            border: round $warning;
        }
        """
        TAB_ORDER = ("overview", "fixes", "self_update", "diagnostics")
        BINDINGS = [
            Binding("ctrl+s", "apply", "Apply"),
            Binding("q", "cancel", "Cancel"),
            Binding("escape", "cancel", "Cancel", show=False),
            Binding("a", "all", "Select all"),
            Binding("n", "none", "Select none"),
            Binding("u", "run_self_update", "Run update"),
            Binding("left", "prev_tab", "Prev tab"),
            Binding("right", "next_tab", "Next tab"),
            Binding("1", "show_tab('overview')", "Overview", show=False),
            Binding("2", "show_tab('fixes')", "Fixes", show=False),
            Binding("3", "show_tab('self_update')", "Self-update", show=False),
            Binding("4", "show_tab('diagnostics')", "Diagnostics", show=False),
        ]

        def __init__(self) -> None:
            super().__init__()
            self._update_proc: subprocess.Popen[str] | None = None
            self._update_thread: threading.Thread | None = None

        def compose(self) -> ComposeResult:
            yield Header(show_clock=False)
            with Vertical(id="panel"):
                with TabbedContent(initial="fixes"):
                    with TabPane("Overview", id="overview"):
                        yield Static(
                            Text.from_markup(_format_overview(checks)),
                            classes="pane_text",
                        )
                    with TabPane("Fixes", id="fixes"):
                        with Vertical(id="fixes_grid"):
                            with Horizontal(id="fix_body"):
                                with Vertical(id="fix_left"):
                                    rows = []
                                    for fx in fix_order:
                                        rows.append(
                                            (
                                                Text.from_markup(_fix_row_label(fx)),
                                                fx.id,
                                                fx.selected_default,
                                            )
                                        )
                                    yield SelectionList[str](*rows, id="fixes_list")
                                with Vertical(id="fix_right"):
                                    yield Static("Fix details", id="detail_title")
                                    yield Static("", id="detail_block")
                                    yield Static("Preview", id="preview_title")
                                    yield Static("", id="preview_block")
                            with Horizontal(id="fixes_bottom"):
                                with Vertical(id="apply_controls"):
                                    yield Static(
                                        f"[^s] Apply (0/{total_fixes})",
                                        id="btn_apply_fixes",
                                    )
                                    with Horizontal(id="apply_secondary"):
                                        yield Static("[a] Select all", id="btn_all")
                                        yield Static("[n] Select none", id="btn_none")
                                with Vertical(id="plan_box"):
                                    yield Static("Apply plan", id="plan_title")
                                    yield Static("", id="plan_block")
                    with TabPane("Self-update", id="self_update"):
                        with Vertical(id="self_update_body"):
                            yield Static(
                                Text.from_markup(_format_self_update_static(ctx)),
                                id="self_update_info",
                            )
                            yield Static(
                                "[bold]Press 'u' or click below to run.[/]",
                                id="self_update_hint",
                            )
                            yield Static(
                                "▶ Run update (u)" if ctx.update_cmd else "Run update — unavailable",
                                id="self_update_button",
                                classes="" if ctx.update_cmd else "-disabled",
                            )
                            yield RichLog(
                                highlight=True,
                                markup=True,
                                wrap=True,
                                id="self_update_log",
                            )
                    with TabPane("Diagnostics", id="diagnostics"):
                        yield Static(
                            Text.from_markup(_format_diagnostics(ctx)),
                            classes="pane_text",
                        )
            with Horizontal(id="action_bar"):
                yield Static("[q] Cancel", id="btn_cancel")

        # --- lifecycle ----------------------------------------------

        def on_mount(self) -> None:
            self._sync_focus_to_active_tab()
            self._refresh_detail()
            self._refresh_action_bar()

        def on_tabbed_content_tab_activated(self, event) -> None:
            self._sync_focus_to_active_tab(event.pane.id)
            self._refresh_detail()
            self._refresh_action_bar(event.pane.id)

        def on_selection_list_selection_highlighted(self, _event) -> None:
            self._refresh_detail()

        def on_selection_list_selection_toggled(self, _event) -> None:
            self._refresh_detail()
            self._refresh_action_bar()

        # --- bindings ----------------------------------------------

        def check_action(self, action: str, parameters):
            _ = parameters
            on_fixes = self._active_tab_id() == "fixes"
            on_self_update = self._active_tab_id() == "self_update"
            if action in ("all", "none", "apply"):
                return on_fixes
            if action == "run_self_update":
                return on_self_update
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
                apply_btn = self.query_one("#btn_apply_fixes", Static)
                if total_changes == 0 and cannot_count == 0:
                    apply_btn.update(
                        Text.from_markup("[^s] Apply (no changes)")
                    )
                    apply_btn.add_class("-disabled")
                else:
                    apply_btn.update(
                        Text.from_markup(
                            f"[^s] Apply "
                            f"[bright_green]+{create_count}[/]"
                            f" [bright_red]-{remove_count}[/]"
                            + (f"  [bright_red]!{cannot_count}[/]" if cannot_count else "")
                        )
                    )
                    apply_btn.remove_class("-disabled")
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

            preview_lines = (
                fix.preview_create if intent in {INTENT_CREATE, INTENT_KEEP, INTENT_CANNOT_CREATE, INTENT_ABSENT}
                else fix.preview_remove
            )
            preview.update(
                "\n".join(preview_lines) if preview_lines else "<no preview available>"
            )

        # --- actions ----------------------------------------------

        def action_apply(self) -> None:
            widget = self.query_one("#fixes_list", SelectionList)
            selected = {str(value) for value in widget.selected}
            self.exit(selected)

        def action_cancel(self) -> None:
            self.exit(None)

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
                proc = subprocess.Popen(  # noqa: S603 - command came from ctx
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
            button = self.query_one("#self_update_button", Static)
            button.update("▶ Running… (output below)")
            button.add_class("-disabled")

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
            button = self.query_one("#self_update_button", Static)
            button.update("▶ Run update (u)" if ctx.update_cmd else "Run update — unavailable")
            if ctx.update_cmd:
                button.remove_class("-disabled")

    app = _SetupApp()
    return app.run()


__all__ = ["run_setup_app"]
