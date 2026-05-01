from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any

from rich.text import Text
from textual.widgets import Button, Static, Tab, Tabs

from ...core.constants import COLOR_DYNAMIC_FILE_HEX
from ...core.models import ProjectRow
from ...core.utils import WIDGET_API_ERRORS, fmt_age_short_from_iso
from ...metadata.api import build_project_info_text
from ..query.notes_paths import render_notes_template
from ..widgets import ReadmeMarkdownViewer


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
    readme_create_btn.display = False
    readme_edit_btn.display = False
    notes_create_btn.display = False
    notes_open_btn.display = False
    selected = app._selected_row()
    app._update_readme_tab_state()
    lines: list[str] = []

    if app.side_main_tab == "info":
        if app.side_info_tab == "global":
            lines.extend(app._global_info_lines())
        elif app.side_info_tab == "stats":
            _left, stats = app._cheat_columns()
            lines.append(stats)
        elif app.side_info_tab == "cheat":
            cheat, _right = app._cheat_columns()
            lines.append(cheat)
        elif app.side_info_tab == "cache":
            lines.extend(app._cache_info_lines())
        else:
            if app.messages:
                for level, ts, msg in app.messages:
                    if level == "error":
                        prefix = "[bold red]ERR[/]"
                    elif level == "warn":
                        prefix = "[bold yellow]WRN[/]"
                    else:
                        prefix = f"[bold {color_accent_hex}]INF[/]"
                    lines.append(
                        f"[dim]{ts} ({fmt_age_short_from_iso(ts)})[/] {prefix} {app._esc(msg)}"
                    )
            else:
                lines.append("[dim]no recent events[/]")
    elif app.side_main_tab == "settings":
        if app.side_settings_tab in {"table", "table_config", "open"}:
            app._refresh_settings_table()
            lines.append(f"[dim]{app.side_settings_tab} settings active[/]")
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
                    notes_create_btn.display = not notes_exists
                    notes_open_btn.display = notes_exists
                    if not notes_exists:
                        app.side_notes_rendered_path = None
                        placeholder = "# Notes\n\nNotes file not found."
                        if app.side_notes_rendered_text != placeholder:
                            notes_view.document.update(placeholder)
                            app.side_notes_rendered_text = placeholder
                    else:
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
            lines.append(
                build_project_info_text(
                    base_dir,
                    selected,
                    wip_hotkey=wip_slots.get(selected.path),
                    include_meta_checks=not selected.archived,
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
    subprocess.run(["sh", "-lc", command], cwd=str(base_dir), check=False)


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
            app._run_notes_command(str(app.notes_config.get("open_command", "")), note_path, selected, "open")
        else:
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
    }:
        return
    if button_id in {"side_notes_create", "side_notes_open"}:
        action_id = "notes_create" if button_id == "side_notes_create" else "notes_open"
        app._run_notes_button_action(action_id)
        return
    action_id = "readme_create" if button_id == "side_readme_create" else "readme_edit"
    app._run_readme_button_action(action_id)
