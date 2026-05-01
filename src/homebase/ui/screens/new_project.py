from __future__ import annotations

import difflib
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from ...cache.api import cache_load_rows
from ...config.prefs import load_new_project_defaults, load_post_command_options
from ...core.constants import (
    ACTION_ACCEPT,
    ACTION_CANCEL,
    ARCHIVE_DIR_NAME,
    COLLISION_RED_RAMP,
)
from ...workspace.projects import discover_copier_templates, resolve_new_project_name
from ...workspace.rows import collect_workspace_rows
from .tag_plan import TagPlanScreen

# Tmux helpers.


class NewProjectScreen(ModalScreen[dict[str, str | None] | None]):
    CSS = """
    Screen {
        align: center middle;
    }
    """
    BINDINGS = [
        ("tab", "next_section", "Next section"),
        ("shift+tab", "prev_section", "Previous section"),
        ("up", "move_up", "Up"),
        ("down", "move_down", "Down"),
        ("space", "toggle", "Toggle"),
        ("ctrl+t", "edit_tags", "Edit tags"),
        ("enter", ACTION_ACCEPT, "Create"),
        ("ctrl+q", ACTION_CANCEL, "Cancel"),
        ("escape", ACTION_CANCEL, "Cancel"),
    ]

    def __init__(self, base_dir_ref: Path, allow_stay_in_b: bool = True) -> None:
        super().__init__()
        self.base_dir_ref = base_dir_ref
        self.allow_stay_in_b = bool(allow_stay_in_b)
        self.templates = discover_copier_templates(base_dir_ref)
        self.post_options = load_post_command_options(base_dir_ref)
        defaults = load_new_project_defaults(base_dir_ref)
        self.name_options: list[tuple[str, str]] = [
            ("date_prefix", "prefix yyyy-dd-mm_"),
            ("tmp_suffix", "append .tmp suffix"),
        ]
        self.focus_section = 0
        self.name_option_index = 0
        self.template_index = 0
        name_option_defaults = defaults.get("name_options", [])
        name_option_values = (
            [str(v).strip() for v in name_option_defaults if str(v).strip()]
            if isinstance(name_option_defaults, list)
            else []
        )
        known_name_options = {k for k, _lbl in self.name_options}
        self.selected_name_options: set[str] = {
            k for k in name_option_values if k in known_name_options
        }

        post_defaults = defaults.get("post_commands", [])
        post_values = (
            [str(v).strip() for v in post_defaults if str(v).strip()]
            if isinstance(post_defaults, list)
            else []
        )
        selected_post: set[str] = set()
        for opt in self.post_options:
            if opt.command in post_values:
                selected_post.add(opt.key)
        self.selected_post_options = selected_post
        self.post_index = 0
        tags_defaults = defaults.get("tags", [])
        self.selected_tags = (
            {str(v).strip() for v in tags_defaults if str(v).strip()}
            if isinstance(tags_defaults, list)
            else set()
        )
        self.behavior_options: list[tuple[str, str]] = [
            ("open", "exit b and enter folder"),
            ("stay", "stay in b"),
        ]
        self.behavior_index = 0

        template_default = defaults.get("template")
        template_value = (
            str(template_default).strip() if template_default is not None else ""
        )
        template_options = [None, *self.templates]
        if template_value and template_value in self.templates:
            self.template_index = template_options.index(template_value)

        behavior_default = (
            str(defaults.get("after_create", "open")).strip() or "open"
        )
        behavior_keys = [k for k, _lbl in self.behavior_options]
        if behavior_default in behavior_keys:
            self.behavior_index = behavior_keys.index(behavior_default)
        if not self.allow_stay_in_b:
            self.behavior_index = 0

    def _section_count(self) -> int:
        return 6 if self.allow_stay_in_b else 5

    def compose(self) -> ComposeResult:
        with Vertical(id="new_project_box"):
            yield Static("[bold]Create new project[/]")
            with Horizontal(id="new_body"):
                with VerticalScroll(id="new_left"):
                    yield Input(placeholder="folder name", id="new_name")
                    yield Static("", id="new_name_options")
                    yield Static("", id="new_template")
                    yield Static("", id="new_post")
                    yield Static("", id="new_tags")
                    if self.allow_stay_in_b:
                        yield Static("", id="new_behavior")
                with VerticalScroll(id="new_right"):
                    yield Static("", id="new_status")
            yield Static("", id="new_plan")
            yield Static(
                "tab/shift+tab section  up/down move  space toggle multi  ctrl+t tags  enter confirm  esc/^q cancel",
                id="new_hotkeys",
            )

    def on_mount(self) -> None:
        self._set_section_focus()
        self._refresh()

    def _set_section_focus(self) -> None:
        name_input = self.query_one("#new_name", Input)
        if self.focus_section == 0:
            name_input.focus()
        else:
            name_input.blur()

    def _template_preview_lines(
        self, template_name: str | None, limit: int = 18
    ) -> list[str]:
        if not template_name:
            return []

        template_dir = self.base_dir_ref / ".copier" / template_name
        if not template_dir.is_dir():
            return ["[red]template files: template directory missing[/]"]

        collected: list[Path] = []
        try:
            for p in sorted(template_dir.rglob("*"), key=lambda x: str(x).lower()):
                if p.is_dir():
                    continue
                collected.append(p.relative_to(template_dir))
                if len(collected) >= limit:
                    break
        except (OSError, ValueError) as exc:
            return [f"[red]template files: failed to read ({exc})[/]"]

        lines = ["[bold]template files[/]"]
        if not collected:
            lines.append("[dim](empty template)[/]")
            return lines

        for rel in collected:
            lines.append(f"[white]- {rel.as_posix()}[/]")

        more = 0
        try:
            total_files = sum(1 for p in template_dir.rglob("*") if p.is_file())
            more = max(0, total_files - len(collected))
        except OSError:
            more = 0
        if more > 0:
            lines.append(f"[dim]... +{more} more[/]")
        return lines

    def _current_target(self) -> Path | None:
        name = self.query_one("#new_name", Input).value.strip()
        if not name:
            return None
        add_date_prefix = "date_prefix" in self.selected_name_options
        add_tmp_suffix = "tmp_suffix" in self.selected_name_options
        try:
            resolved = resolve_new_project_name(
                name, add_date_prefix, add_tmp_suffix
            )
        except ValueError:
            return None
        return self.base_dir_ref / resolved

    def _target_exists(self) -> bool:
        target = self._current_target()
        return bool(target and target.exists())

    def _workspace_tag_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        active_rows, archived_rows, _ts = cache_load_rows(self.base_dir_ref)
        if not active_rows and not archived_rows:
            active_rows, archived_rows = collect_workspace_rows(
                self.base_dir_ref,
                include_git_dirty=False,
            )
        for row in active_rows + archived_rows:
            for tag in row.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return counts

    def action_edit_tags(self) -> None:
        if self._target_exists():
            self._refresh()
            return
        counts = self._workspace_tag_counts()
        all_tags = sorted(set(counts.keys()) | set(self.selected_tags))
        presence = {
            tag: ("all" if tag in self.selected_tags else "none")
            for tag in all_tags
        }
        self.app.push_screen(
            TagPlanScreen(all_tags, presence, counts, mode="add_only"),
            self._on_new_tags_plan,
        )

    def _on_new_tags_plan(self, plan: dict[str, str] | None) -> None:
        if plan is None:
            self._refresh()
            return
        updated: set[str] = set(self.selected_tags)
        for tag, op in plan.items():
            if op == "add":
                updated.add(tag)
            elif op == "remove":
                updated.discard(tag)
            else:
                # keep: no change
                pass
        self.selected_tags = updated
        self._refresh()

    def _existing_name_suggestions(
        self, query: str, limit: int = 5
    ) -> list[tuple[str, int]]:
        q = query.strip().lower()
        if len(q) < 3:
            return []

        names: list[str] = []
        for p in self.base_dir_ref.iterdir():
            if (
                not p.is_dir()
                or p.name.startswith(".")
                or p.name == ARCHIVE_DIR_NAME
            ):
                continue
            names.append(p.name)

        scored: list[tuple[float, str]] = []
        for name in names:
            n = name.lower()
            ratio = difflib.SequenceMatcher(None, q, n).ratio()
            if q in n:
                ratio = max(ratio, 0.70)
            if n.startswith(q):
                ratio = max(ratio, 0.85)
            if n == q:
                ratio = 1.0
            if ratio >= 0.35:
                score = ratio
                scored.append((score, name))

        scored.sort(key=lambda x: (-x[0], x[1]))
        return [(name, int(round(score * 100))) for score, name in scored[:limit]]

    def _template_options(self) -> list[str | None]:
        return [None, *self.templates]

    def _current_template(self) -> str | None:
        options = self._template_options()
        if self.template_index >= len(options):
            self.template_index = 0
        return options[self.template_index]



    def _current_behavior(self) -> str:
        if self.behavior_index >= len(self.behavior_options):
            self.behavior_index = 0
        return self.behavior_options[self.behavior_index][0]

    def _sync_name_for_name_options(self) -> None:
        input_widget = self.query_one("#new_name", Input)
        current = input_widget.value.strip()
        if not current:
            return
        add_date_prefix = "date_prefix" in self.selected_name_options
        add_tmp_suffix = "tmp_suffix" in self.selected_name_options
        updated = resolve_new_project_name(current, add_date_prefix, add_tmp_suffix)
        if updated != input_widget.value:
            input_widget.value = updated

    def _refresh(self) -> None:
        exists_now = self._target_exists()

        name_lines = ["Name options (multi select):"]
        for idx, (key, label) in enumerate(self.name_options):
            cursor = (
                ">"
                if self.focus_section == 1 and idx == self.name_option_index
                else " "
            )
            mark = "(x)" if key in self.selected_name_options else "( )"
            name_lines.append(f"{cursor} {mark} {label}")
        self.query_one("#new_name_options", Static).update("\n".join(name_lines))

        template_lines = ["Copier template (single select):"]
        template_options = self._template_options()
        for idx, item in enumerate(template_options):
            cursor = (
                ">"
                if self.focus_section == 2 and idx == self.template_index
                else " "
            )
            mark = "(x)" if idx == self.template_index else "( )"
            label = "(none)" if item is None else item
            template_lines.append(f"{cursor} {mark} {label}")
        if exists_now:
            template_lines = [f"[dim]{line}[/]" for line in template_lines]
        self.query_one("#new_template", Static).update("\n".join(template_lines))

        post_lines = ["Post commands (multi select):"]
        for idx, opt in enumerate(self.post_options):
            cursor = (
                ">" if self.focus_section == 3 and idx == self.post_index else " "
            )
            mark = "(x)" if opt.key in self.selected_post_options else "( )"
            post_lines.append(f"{cursor} {mark} {opt.label}")
        if exists_now:
            post_lines = [f"[dim]{line}[/]" for line in post_lines]
        self.query_one("#new_post", Static).update("\n".join(post_lines))

        tag_summary = (
            ", ".join(sorted(self.selected_tags))
            if self.selected_tags
            else "(none)"
        )
        tags_lines = [
            "Tags (add only):",
            f"{('>' if self.focus_section == 4 else ' ')} edit tags (space/ctrl+t)",
            f"  selected: {tag_summary}",
        ]
        if exists_now:
            tags_lines = [f"[dim]{line}[/]" for line in tags_lines]
        self.query_one("#new_tags", Static).update("\n".join(tags_lines))

        if self.allow_stay_in_b:
            behavior_lines = ["After create (single select):"]
            for idx, (_key, label) in enumerate(self.behavior_options):
                cursor = (
                    ">"
                    if self.focus_section == 5 and idx == self.behavior_index
                    else " "
                )
                mark = "(x)" if idx == self.behavior_index else "( )"
                behavior_lines.append(f"{cursor} {mark} {label}")
            if exists_now:
                behavior_lines = [f"[dim]{line}[/]" for line in behavior_lines]
            self.query_one("#new_behavior", Static).update(
                "\n".join(behavior_lines)
            )

        name = self.query_one("#new_name", Input).value.strip()
        add_date_prefix = "date_prefix" in self.selected_name_options
        add_tmp_suffix = "tmp_suffix" in self.selected_name_options
        selected_template = self._current_template() or "(none)"
        selected_post = [
            opt.label
            for opt in self.post_options
            if opt.key in self.selected_post_options
        ]
        resolved_name = ""
        target = None
        if not name:
            path_preview = "-"
            exists_marker = "-"
        else:
            try:
                resolved_name = resolve_new_project_name(
                    name, add_date_prefix, add_tmp_suffix
                )
                target = self.base_dir_ref / resolved_name
                path_preview = str(target)
                exists_marker = (
                    "[bold red]YES[/]" if target.exists() else "[bold green]no[/]"
                )
            except ValueError as exc:
                path_preview = f"[red]invalid: {exc}[/]"
                exists_marker = "-"

        post_cmd_lines = (
            [f"  - {label}" for label in selected_post]
            if selected_post
            else ["  - (none)"]
        )
        info_lines = [
            f"[bold green]current[/]: {resolved_name or '-'}",
            f"[bold green]path[/]: [dim]{path_preview}[/]",
            f"[bold green]exists[/]: {exists_marker}",
            f"[bold green]template[/]: {selected_template}",
            f"[bold green]tags[/]: {', '.join(sorted(self.selected_tags)) or '-'}",
        ]
        if selected_post:
            info_lines += ["[bold green]post commands[/]:"]
            info_lines += [f"[yellow]{line}[/]" for line in post_cmd_lines]

        fuzzy_query = ""
        if name:
            try:
                fuzzy_query = resolve_new_project_name(name, False, False)
            except ValueError:
                fuzzy_query = ""
        suggestions = self._existing_name_suggestions(fuzzy_query, limit=5)
        if suggestions:
            info_lines += [
                "",
                "[dim]------------------------------------------------------------[/]",
                "[bold yellow]similar matches[/]",
            ]
            for item, pct in suggestions:
                # Pick a red-ramp shade. 95+ = full red, falling off in 10pp steps.
                bucket = max(0, min(len(COLLISION_RED_RAMP) - 1, (100 - pct) // 10))
                style = COLLISION_RED_RAMP[bucket]
                info_lines += [f"[{style}]- {item} ({pct}%)[/]"]

        template_preview = self._template_preview_lines(self._current_template())
        if template_preview:
            info_lines += [
                "",
                "[dim]------------------------------------------------------------[/]",
            ] + template_preview
        self.query_one("#new_status", Static).update("\n".join(info_lines))

        action_key = self._current_behavior()
        plan = "Will "
        if not name or not target:
            plan += "wait for valid name"
        elif target.exists():
            plan += f"open existing [bold cyan]{resolved_name}[/] and close b"
        elif action_key == "stay":
            plan += f"create [bold green]{resolved_name}[/] and stay in b"
        else:
            plan += f"create [bold green]{resolved_name}[/], then [bold cyan]open it[/] and close b"
        self.query_one("#new_plan", Static).update(plan)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "new_name":
            self._refresh()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "new_name":
            self.action_accept()

    def action_next_section(self) -> None:
        self.focus_section = (self.focus_section + 1) % self._section_count()
        self._set_section_focus()
        self._refresh()

    def action_prev_section(self) -> None:
        self.focus_section = (self.focus_section - 1) % self._section_count()
        self._set_section_focus()
        self._refresh()

    def action_toggle(self) -> None:
        exists_now = self._target_exists()
        if self.focus_section == 1:
            key = self.name_options[self.name_option_index][0]
            if key in self.selected_name_options:
                self.selected_name_options.remove(key)
            else:
                self.selected_name_options.add(key)
            self._sync_name_for_name_options()
            self._refresh()
            return
        disabled_sections = {2, 3, 4}
        if self.allow_stay_in_b:
            disabled_sections.add(5)
        if exists_now and self.focus_section in disabled_sections:
            self._refresh()
            return
        if self.focus_section == 2:
            opts = self._template_options()
            if opts:
                self.template_index = (self.template_index + 1) % len(opts)
            self._refresh()
            return
        if self.focus_section == 3 and self.post_options:
            key = self.post_options[self.post_index].key
            if key in self.selected_post_options:
                self.selected_post_options.remove(key)
            else:
                self.selected_post_options.add(key)
            self._refresh()
            return
        if self.focus_section == 4:
            self.action_edit_tags()
            return
        if self.allow_stay_in_b and self.focus_section == 5:
            self.behavior_index = (self.behavior_index + 1) % len(
                self.behavior_options
            )
            self._refresh()
            return

    def action_move_up(self) -> None:
        exists_now = self._target_exists()
        if self.focus_section == 1 and self.name_options:
            self.name_option_index = (self.name_option_index - 1) % len(
                self.name_options
            )
        elif self.focus_section == 2 and not exists_now:
            opts = self._template_options()
            self.template_index = (self.template_index - 1) % len(opts)
        elif self.focus_section == 3 and not exists_now:
            if self.post_options:
                self.post_index = (self.post_index - 1) % len(self.post_options)
        elif self.allow_stay_in_b and self.focus_section == 5 and not exists_now:
            self.behavior_index = (self.behavior_index - 1) % len(
                self.behavior_options
            )
        self._refresh()

    def action_move_down(self) -> None:
        exists_now = self._target_exists()
        if self.focus_section == 1 and self.name_options:
            self.name_option_index = (self.name_option_index + 1) % len(
                self.name_options
            )
        elif self.focus_section == 2 and not exists_now:
            opts = self._template_options()
            self.template_index = (self.template_index + 1) % len(opts)
        elif self.focus_section == 3 and not exists_now:
            if self.post_options:
                self.post_index = (self.post_index + 1) % len(self.post_options)
        elif self.allow_stay_in_b and self.focus_section == 5 and not exists_now:
            self.behavior_index = (self.behavior_index + 1) % len(
                self.behavior_options
            )
        self._refresh()

    def action_accept(self) -> None:
        folder_name = self.query_one("#new_name", Input).value.strip()
        if not folder_name:
            self.query_one("#new_status", Static).update(
                "[red]folder name is empty[/]"
            )
            return
        add_date_prefix = "date_prefix" in self.selected_name_options
        add_tmp_suffix = "tmp_suffix" in self.selected_name_options
        try:
            # Validate that the name resolves; the result is unused
            # because we pass the raw inputs back through the dismiss
            # payload and let the caller re-resolve.
            resolve_new_project_name(folder_name, add_date_prefix, add_tmp_suffix)
        except ValueError as exc:
            self.query_one("#new_status", Static).update(f"[red]{exc}[/]")
            return
        chosen_template = self._current_template()
        selected_commands = [
            opt.command
            for opt in self.post_options
            if opt.key in self.selected_post_options
        ]
        self.dismiss(
            {
                "folder_name": folder_name,
                "add_date_prefix": "1" if add_date_prefix else "0",
                "add_tmp_suffix": "1" if add_tmp_suffix else "0",
                "template": chosen_template,
                "post_commands": "\n".join(selected_commands),
                "tags": "\n".join(sorted(self.selected_tags)),
                "after_create": (
                    self._current_behavior() if self.allow_stay_in_b else "open"
                ),
            }
        )

    def action_cancel(self) -> None:
        self.dismiss(None)



