from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.widgets import Button, Static, Tab, Tabs

from ...core.constants import COLOR_DYNAMIC_FILE_HEX
from ...core.models import ProjectRow
from ...core.utils import (
    WIDGET_API_ERRORS,
    existing_path_case_mismatch,
    fmt_age_short_from_iso,
)
from ...workspace.project_info import project_info_text
from ..query.notes_paths import render_notes_template
from ..widgets import ReadmeMarkdownViewer
from .hooks_panel import render_hooks_panel


def update_readme_tab_state(app: Any) -> None:
    selected_tabs = app.query_one("#side_selected_tabs", Tabs)
    readme_available = app._selected_readme_path() is not None
    notes_available = app._selected_notes_path() is not None
    for tab in selected_tabs.query(Tab):
        tab_id = str(getattr(tab, "id", "") or "")
        if tab_id not in {"readme", "notes"}:
            continue
        try:
            tab.disabled = False
        except WIDGET_API_ERRORS:
            pass
        try:
            if tab_id == "readme":
                tab.label = (
                    Text("README.md", style=COLOR_DYNAMIC_FILE_HEX)
                    if readme_available
                    else Text("README.md", style="dim")
                )
            else:
                tab.label = (
                    Text("NOTES", style=COLOR_DYNAMIC_FILE_HEX)
                    if notes_available
                    else Text("NOTES", style="dim")
                )
        except WIDGET_API_ERRORS:
            pass


def refresh_side(app: Any, *, base_dir: Path, color_accent_hex: str, level_warn: str) -> None:
    side = app.query_one("#side_body", Static)
    readme_view = app.query_one("#side_readme", ReadmeMarkdownViewer)
    notes_view = app.query_one("#side_notes", ReadmeMarkdownViewer)
    readme_create_btn = app.query_one("#side_readme_create", Button)
    readme_edit_btn = app.query_one("#side_readme_edit", Button)
    notes_create_btn = app.query_one("#side_notes_create", Button)
    notes_open_btn = app.query_one("#side_notes_open", Button)
    global_reload_btn = app.query_one("#side_global_config_reload", Button)
    global_edit_btn = app.query_one("#side_global_config_edit", Button)
    global_info = app.query_one("#side_global_info", Static)
    readme_create_btn.display = False
    readme_edit_btn.display = False
    notes_create_btn.display = False
    notes_open_btn.display = False
    global_reload_btn.display = False
    global_edit_btn.display = False
    selected = app._selected_row()
    app._update_readme_tab_state()
    lines: list[str] = []

    if app.side_main_tab == "info":
        if app.side_info_tab == "global":
            lines.extend(app._global_info_lines())
        elif app.side_info_tab == "stats":
            lines.extend(app._stats_and_context_lines())
        elif app.side_info_tab == "cheat":
            cheat, _right = app._cheat_columns()
            lines.append(cheat)
        elif app.side_info_tab == "cache":
            lines.extend(app._cache_info_lines())
            lines.append("[dim]----------------------------------------[/]")
            lines.append("[cyan]managed processes[/]:")
            lines.extend(app._managed_process_info_lines())
        elif app.side_info_tab == "hooks":
            lines.extend(render_hooks_panel(app).splitlines())
        else:
            if app.messages:
                for level, ts, msg in app.messages:
                    if level == "error":
                        prefix = "[bold red]ERR[/]"
                    elif level == "warn":
                        prefix = "[bold yellow]WRN[/]"
                    else:
                        prefix = f"[bold {color_accent_hex}]INF[/]"
                    msg_lines = str(msg).split("\n")
                    head = msg_lines[0]
                    lines.append(
                        f"[dim]{ts} ({fmt_age_short_from_iso(ts)})[/] {prefix} {app._esc(head)}"
                    )
                    for cont in msg_lines[1:]:
                        lines.append(f"[dim]    {app._esc(cont)}[/]")
            else:
                lines.append("[dim]no recent events[/]")
    elif app.side_main_tab == "settings":
        if app.side_settings_tab in {"table", "table_config", "open", "global"}:
            app._refresh_settings_table()
            lines.append(f"[dim]{app.side_settings_tab} settings active[/]")
            if app.side_settings_tab == "global":
                global_info.update(app._global_config_status_text())
                global_reload_btn.display = True
                global_edit_btn.display = True
        else:
            lines.append("[dim]no settings view[/]")
    elif not selected:
        lines.append("[dim]no focused project[/]")
    else:
        if app.side_selected_tab in {"git", "files"}:
            needs_refresh = (
                app.side_detail_row != selected.path
                or not app.side_git_text
                or not app.side_files_text
            )
            if needs_refresh:
                app._refresh_selected_details(log_success=False)

        if app.side_selected_tab == "readme":
            readme_path = app._selected_readme_path()
            if readme_path is None:
                app.side_readme_source_path = None
                app.side_readme_rendered_path = None
                placeholder = "# README.md\n\nREADME.md not found."
                if app.side_readme_rendered_text != placeholder:
                    readme_view.document.update(placeholder)
                    app.side_readme_rendered_text = placeholder
                readme_create_btn.display = True
            else:
                app.side_readme_source_path = readme_path
                readme_create_btn.display = False
                readme_edit_btn.display = True
                try:
                    readme_text = readme_path.read_text()
                except (OSError, UnicodeDecodeError) as exc:
                    app._show_runtime_error("load README.md", exc)
                    readme_text = "# README.md\n\nFailed to read README.md."
                if (
                    app.side_readme_rendered_path != readme_path
                    or app.side_readme_rendered_text != readme_text
                ):
                    readme_view.document.update(readme_text)
                    app.side_readme_rendered_path = readme_path
                    app.side_readme_rendered_text = readme_text
        elif app.side_selected_tab == "notes":
            selected_notes = app._selected_row()
            try:
                notes_create_btn.label = "Create note"
                notes_open_btn.label = "Open note"
            except WIDGET_API_ERRORS:
                pass
            if selected_notes is None:
                app.side_notes_source_path = None
                app.side_notes_rendered_path = None
                placeholder = "# Notes\n\nNo focused project."
                if app.side_notes_rendered_text != placeholder:
                    notes_view.document.update(placeholder)
                    app.side_notes_rendered_text = placeholder
            else:
                try:
                    notes_path = app._resolve_notes_path_for_row(selected_notes)
                except (OSError, ValueError, RuntimeError) as exc:
                    app.side_notes_source_path = None
                    app.side_notes_rendered_path = None
                    app._set_runtime_status(f"notes path error: {exc}", level_warn, ttl_s=6.0)
                    placeholder = "# Notes\n\nNotes path is not configured correctly."
                    if app.side_notes_rendered_text != placeholder:
                        notes_view.document.update(placeholder)
                        app.side_notes_rendered_text = placeholder
                    notes_create_btn.display = False
                    notes_open_btn.display = False
                else:
                    app.side_notes_source_path = notes_path
                    try:
                        notes_exists = notes_path.is_file()
                    except OSError:
                        notes_exists = False
                    actual_name = (
                        existing_path_case_mismatch(notes_path)
                        if notes_exists
                        else None
                    )
                    if actual_name is not None:
                        notes_create_btn.display = False
                        notes_open_btn.display = False
                        app.side_notes_rendered_path = None
                        error_text = (
                            "# E — Notes case mismatch\n\n"
                            "**ERROR**: the note exists on disk but the filename "
                            "does not match the project name in case.\n\n"
                            f"- Expected note file: `{notes_path.name}`\n"
                            f"- On-disk file:       `{actual_name}`\n"
                            f"- Parent directory:   `{notes_path.parent}`\n\n"
                            "Opening this note would create a duplicate in case-"
                            "insensitive editors (e.g. Obsidian). Rename either "
                            "the project or the note so the case matches exactly, "
                            "then reopen this view."
                        )
                        if app.side_notes_rendered_text != error_text:
                            notes_view.document.update(error_text)
                            app.side_notes_rendered_text = error_text
                    elif not notes_exists:
                        notes_create_btn.display = True
                        notes_open_btn.display = False
                        app.side_notes_rendered_path = None
                        placeholder = "# Notes\n\nNotes file not found."
                        if app.side_notes_rendered_text != placeholder:
                            notes_view.document.update(placeholder)
                            app.side_notes_rendered_text = placeholder
                    else:
                        notes_create_btn.display = False
                        notes_open_btn.display = True
                        try:
                            notes_text = notes_path.read_text()
                        except (OSError, UnicodeDecodeError) as exc:
                            app._show_runtime_error("load notes markdown", exc)
                            notes_text = "# Notes\n\nFailed to read notes markdown."
                        if (
                            app.side_notes_rendered_path != notes_path
                            or app.side_notes_rendered_text != notes_text
                        ):
                            notes_view.document.update(notes_text)
                            app.side_notes_rendered_path = notes_path
                            app.side_notes_rendered_text = notes_text
        elif app.side_selected_tab == "git":
            readme_create_btn.display = False
            lines.append(app.side_git_text or "[dim]git details not loaded yet[/]")
        elif app.side_selected_tab == "events":
            readme_create_btn.display = False
            lines.append(app._build_side_project_events_text(selected))
        elif app.side_selected_tab == "files":
            readme_create_btn.display = False
            lines.append(app.side_files_text or "[dim]file details not loaded yet[/]")
        else:
            readme_create_btn.display = False
            wip_slots = {row.path: i for i, row in enumerate(app._wip_rows_sorted()[:9], start=1)}
            cached_health: tuple[str, str] | None = None
            cached_entry = app.metadata_health_cache.get(selected.path)
            if cached_entry is not None:
                cached_health = (str(cached_entry[0]), str(cached_entry[1]))
            lines.append(
                project_info_text(
                    selected,
                    wip_hotkey=wip_slots.get(selected.path),
                    include_meta_checks=not selected.archived,
                    cached_meta_health=cached_health,
                )
            )
            if selected.archived:
                lines.append("[cyan]preview[/]: [dim]disabled in archive overview for speed[/]")
            else:
                lines.append("[cyan]preview[/]:")
                lines.extend(app._preview_entries(selected.path))

    side.update("\n".join(lines))
    app._refresh_wip_bar()
    app._refresh_search_display()


def run_notes_command(
    app: Any,
    command_template: str,
    note_path: Path,
    row: ProjectRow,
    op: str,
    *,
    base_dir: Path,
) -> None:
    template = str(command_template).strip()
    if not template:
        raise ValueError(f"notes.{op}_command is empty")
    context = app._notes_template_context(row)
    context["NOTE_PATH"] = str(note_path)
    context["note_path"] = str(note_path)
    context["NOTE_PATH_Q"] = shlex.quote(str(note_path))
    context["note_path_q"] = context["NOTE_PATH_Q"]
    command = render_notes_template(template, context)
    app._start_managed_shell_command(
        command,
        cwd=base_dir,
        label=f"notes {op}: {row.name}",
        wait=False,
        terminate_on_quit=True,
    )


def run_notes_button_action(app: Any, action_id: str, *, level_warn: str) -> None:
    if action_id not in {"notes_create", "notes_open"}:
        return
    selected = app._selected_row()
    if selected is None:
        app._set_runtime_status("no focused project", level_warn, ttl_s=4.0)
        return
    try:
        note_path = app._resolve_notes_path_for_row(selected)
    except (OSError, ValueError, RuntimeError) as exc:
        app._show_runtime_error("resolve notes path", exc)
        return
    try:
        if action_id == "notes_open":
            if not note_path.is_file():
                app._set_runtime_status("Notes file not found for open", level_warn, ttl_s=6.0)
                return
            actual_name = existing_path_case_mismatch(note_path)
            if actual_name is not None:
                app._show_runtime_error(
                    "open notes markdown",
                    FileExistsError(
                        f"case mismatch: expected '{note_path.name}', "
                        f"on-disk '{actual_name}' in {note_path.parent}"
                    ),
                )
                return
            app._mark_row_active(selected.path)
            app._run_notes_command(str(app.notes_config.get("open_command", "")), note_path, selected, "open")
        else:
            actual_name = existing_path_case_mismatch(note_path)
            if actual_name is not None:
                app._show_runtime_error(
                    "create notes markdown",
                    FileExistsError(
                        f"case mismatch: expected '{note_path.name}', "
                        f"on-disk '{actual_name}' in {note_path.parent}"
                    ),
                )
                return
            app._mark_row_active(selected.path)
            app._run_notes_command(str(app.notes_config.get("create_command", "")), note_path, selected, "create")
    except (OSError, ValueError, RuntimeError) as exc:
        app._show_runtime_error("run notes command", exc)
        return
    app._refresh_side()


def run_readme_button_action(app: Any, action_id: str, *, level_warn: str) -> None:
    if action_id not in {"readme_create", "readme_edit"}:
        return
    selected = app._selected_row()
    if selected is None:
        app._set_runtime_status("no focused project", level_warn, ttl_s=4.0)
        return
    if selected.packed:
        app._set_runtime_status("README.md cannot be created for packed archive", level_warn, ttl_s=6.0)
        return
    try:
        if not selected.path.is_dir():
            app._set_runtime_status("README.md target is not a directory", level_warn, ttl_s=6.0)
            return
    except OSError as exc:
        app._show_runtime_error("check README target dir", exc)
        return

    readme_path = selected.path / "README.md"
    try:
        if action_id == "readme_create":
            readme_path.touch(exist_ok=True)
        elif not readme_path.is_file():
            app._set_runtime_status("README.md not found for edit", level_warn, ttl_s=6.0)
            return
        app._mark_row_active(selected.path)
        app._open_editor_for_path(readme_path)
    except (OSError, ValueError) as exc:
        op = "create/edit README.md in editor" if action_id == "readme_create" else "edit README.md in editor"
        app._show_runtime_error(op, exc)
        return
    app._refresh_side()


def on_button_pressed(app: Any, event: Any) -> None:
    button_id = str(getattr(getattr(event, "button", None), "id", "") or "")
    if button_id not in {
        "side_readme_create",
        "side_readme_edit",
        "side_notes_create",
        "side_notes_open",
        "side_global_config_reload",
        "side_global_config_edit",
    }:
        return
    if button_id == "side_global_config_reload":
        app._reload_global_config()
        return
    if button_id == "side_global_config_edit":
        app._edit_global_config_and_reload()
        return
    if button_id in {"side_notes_create", "side_notes_open"}:
        action_id = "notes_create" if button_id == "side_notes_create" else "notes_open"
        app._run_notes_button_action(action_id)
        return
    action_id = "readme_create" if button_id == "side_readme_create" else "readme_edit"
    app._run_readme_button_action(action_id)
