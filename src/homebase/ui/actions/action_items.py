from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from ...core.constants import BUILTIN_ACTIONS
from ...core.models import Action, ProjectRow
from ...core.utils import existing_path_case_mismatch
from ...notes.log_md import NoteValidationError, insert_log_entry, validate_note
from ..screens.multiline_input import MultilineInputScreen
from . import template as action_template


def custom_actions_for_scope(
    app: Any,
    scope: str,
    *,
    color_accent_hex: str,
) -> list[tuple[str, str]]:
    normal: list[tuple[str, str]] = []
    list_actions: list[tuple[str, str]] = []
    note_actions: list[tuple[str, str]] = []
    for act in app.ctx.actions.values():
        if act.source == "builtin" or act.scope != scope:
            continue
        cid = act.id
        label = act.label
        is_list_action = act.kind == "filepicker"
        is_note_action = act.kind == "note"
        if is_note_action:
            plain_label = app._esc(label)
            rendered_label = f"[#FFB347]{plain_label}[/] [dim](note)[/]"
        elif is_list_action:
            plain_label = app._esc(label)
            rendered_label = f"[#40E0D0]{plain_label}[/] [dim](filepicker)[/]"
        else:
            rendered_label = f"[{color_accent_hex}]{app._esc(label)}[/]"
        target = (
            cid,
            rendered_label,
        )
        if is_note_action:
            note_actions.append(target)
        elif is_list_action:
            list_actions.append(target)
        else:
            normal.append(target)
    return normal + list_actions + note_actions


def custom_hotkey_target_map(app: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for binding in app.custom_hotkeys:
        hotkey = str(binding.get("hotkey", "")).strip().lower()
        target = str(binding.get("target", "")).strip()
        if not hotkey or not target or hotkey in out:
            continue
        out[hotkey] = target
    return out


def hotkey_target_label_map(app: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for binding in app.custom_hotkeys:
        hotkey = str(binding.get("hotkey", "")).strip()
        target = str(binding.get("target", "")).strip()
        if not hotkey or not target or target in out:
            continue
        out[target] = hotkey
    return out


def hotbar_targets(app: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for binding in app.custom_hotkeys:
        if not bool(binding.get("hotbar", False)):
            continue
        target = str(binding.get("target", "")).strip()
        if not target or target in seen:
            continue
        seen.add(target)
        out.append(target)
    return out


def hotbar_target_custom_label_map(app: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for binding in app.custom_hotkeys:
        target = str(binding.get("target", "")).strip()
        label = str(binding.get("label", "")).strip()
        if not target or not label or target in out:
            continue
        out[target] = label
    return out


def hotbar_target_style_rules_map(app: Any) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    for binding in app.custom_hotkeys:
        if not bool(binding.get("hotbar", False)):
            continue
        target = str(binding.get("target", "")).strip()
        if not target or target in out:
            continue
        raw_style = binding.get("style", [])
        if not isinstance(raw_style, list):
            continue
        style_rows: list[dict[str, str]] = []
        for raw_rule in raw_style:
            if not isinstance(raw_rule, dict):
                continue
            bg_color = str(raw_rule.get("bg_color", "")).strip()
            fg_color = str(raw_rule.get("fg_color", "")).strip()
            when = str(raw_rule.get("when", "")).strip()
            bold = bool(raw_rule.get("bold", False))
            underline = bool(raw_rule.get("underline", False))
            italic = bool(raw_rule.get("italic", False))
            if not when:
                continue
            if not bg_color and not fg_color and not (bold or underline or italic):
                continue
            style_rule: dict[str, str] = {"when": when}
            if bg_color:
                style_rule["bg_color"] = bg_color
            if fg_color:
                style_rule["fg_color"] = fg_color
            if bold:
                style_rule["bold"] = "1"
            if underline:
                style_rule["underline"] = "1"
            if italic:
                style_rule["italic"] = "1"
            style_rows.append(style_rule)
        if style_rows:
            out[target] = style_rows
    return out


def _builtin_label(action_id: str, fallback: str) -> str:
    meta = BUILTIN_ACTIONS.get(action_id)
    return meta.default_label if meta is not None else fallback


_BULK_PREFLIGHT_KEYS = frozenset(
    {"archive", "restore", "pack", "unpack", "toggle_pack", "delete"}
)


def _target_basics(app: Any, targets: list[ProjectRow]) -> list[tuple[str, str]]:
    if not targets:
        return []
    out: list[tuple[str, str]] = [
        ("tags_set", f"[white]{_builtin_label('tags_set', 'Tags...')}[/]"),
        (
            "reconcile_selection_cache",
            f"[white]{_builtin_label('reconcile_selection_cache', 'Reconcile target cache now')}[/]",
        ),
    ]
    if app.view_mode == "active":
        out.append(
            ("suffix_set", f"[white]{_builtin_label('suffix_set', 'Suffix...')}[/]")
        )
    return out


def _ready_suffix_for_bulk(
    app: Any, key: str, targets: list[ProjectRow]
) -> tuple[bool, str]:
    """Return (include, ready_suffix). include=False to skip the entry."""
    runnable, skipped = app._preflight_bulk_action(key, [r.path for r in targets])
    if not runnable:
        return False, ""
    if skipped:
        return True, f" [dim]({len(runnable)}/{len(targets)} ready)[/]"
    return True, ""


def _new_worktree_valid(targets: list[ProjectRow]) -> bool:
    # Single-target only, must be a live row with a git repo under the
    # configured repo_dir.
    if len(targets) != 1:
        return False
    row = targets[0]
    if getattr(row, "archived", False):
        return False
    if not getattr(row, "repo_dir", ""):
        return False
    repo_subdir = row.path / row.repo_dir
    return (repo_subdir / ".git").exists()


def _view_config_items(app: Any, targets: list[ProjectRow]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for key, label in app.view_config[app.view_mode]["actions"]:
        meta = BUILTIN_ACTIONS.get(key)
        scope = meta.scope if meta is not None else "target"
        if scope == "target" and not targets:
            continue
        ready_suffix = ""
        if scope == "target" and key in _BULK_PREFLIGHT_KEYS:
            include, ready_suffix = _ready_suffix_for_bulk(app, key, targets)
            if not include:
                continue
        if key == "deworktree" and not any(
            getattr(r, "worktree_of", "") for r in targets
        ):
            continue
        if key == "new_worktree" and not _new_worktree_valid(targets):
            continue
        out.append((key, f"[white]{label}[/]{ready_suffix}"))
    return out


def _classify_meta_health(
    targets: list[ProjectRow],
    base_meta_issues: Callable[[Path], list[tuple[str, str, str]]],
) -> tuple[bool, bool]:
    has_review_meta = False
    has_legacy_meta = False
    for row in targets:
        issue_codes = {code for _lvl, code, _msg in base_meta_issues(row.path)}
        if not issue_codes or row.packed:
            continue
        has_review_meta = True
        if "legacy_only" in issue_codes or "legacy_conflict" in issue_codes:
            has_legacy_meta = True
    return has_review_meta, has_legacy_meta


def _meta_review_items(
    targets: list[ProjectRow],
    base_meta_issues: Callable[[Path], list[tuple[str, str, str]]],
) -> list[tuple[str, str]]:
    if not targets:
        return []
    out: list[tuple[str, str]] = [
        ("rename_item", f"[white]{_builtin_label('rename_item', 'Rename item...')}[/]"),
    ]
    has_review_meta, has_legacy_meta = _classify_meta_health(targets, base_meta_issues)
    if has_review_meta:
        out.append(
            (
                "review_meta",
                f"[white]{_builtin_label('review_meta', 'Open .base.yaml and review warnings')}[/]",
            )
        )
    if has_legacy_meta:
        out.append(
            (
                "rename_meta_ext",
                f"[white]{_builtin_label('rename_meta_ext', 'Rename .base.yml -> .base.yaml')}[/]",
            )
        )
    return out


def _global_default_items(app: Any) -> list[tuple[str, str]]:
    out = [
        ("refresh_cache", f"[white]{_builtin_label('refresh_cache', 'Refresh cache')}[/]"),
        (
            "full_reconcile",
            f"[white]{_builtin_label('full_reconcile', 'Full reconcile (force rescan)')}[/]",
        ),
        (
            "reload_global_config",
            f"[white]{_builtin_label('reload_global_config', 'Reload global config')}[/]",
        ),
        (
            "edit_global_config",
            f"[white]{_builtin_label('edit_global_config', 'Edit global config in $EDITOR')}[/]",
        ),
    ]
    if app.active_rows or app.archived_rows:
        out.append(
            (
                "reconcile_all_cache",
                f"[white]{_builtin_label('reconcile_all_cache', 'Reconcile all cached rows now')}[/]",
            )
        )
    return out


def _dedupe_actions(out: list[tuple[str, str]]) -> list[tuple[str, str]]:
    uniq: list[tuple[str, str]] = []
    seen: set[str] = set()
    for aid, label in out:
        if aid in seen:
            continue
        seen.add(aid)
        uniq.append((aid, label))
    return uniq


def _strip_note_actions_on_case_mismatch(
    app: Any, out: list[tuple[str, str]], targets: list[ProjectRow]
) -> list[tuple[str, str]]:
    if not (targets and any(_action_is_note_kind(app, aid) for aid, _ in out)):
        return out
    if not _any_target_note_case_mismatch(app, targets):
        return out
    return [(aid, lbl) for aid, lbl in out if not _action_is_note_kind(app, aid)]


def valid_action_items(
    app: Any,
    *,
    color_accent_hex: str,
    base_meta_issues: Callable[[Path], list[tuple[str, str, str]]],
) -> list[tuple[str, str]]:
    targets = app._target_rows()
    out: list[tuple[str, str]] = []
    out.extend(app._readme_button_actions())
    out.extend(app._notes_button_actions())
    out.extend(_target_basics(app, targets))
    out.extend(_view_config_items(app, targets))
    out.extend(_meta_review_items(targets, base_meta_issues))
    out.extend(_global_default_items(app))
    if targets:
        out.extend(
            custom_actions_for_scope(app, "target", color_accent_hex=color_accent_hex)
        )
    out.extend(
        custom_actions_for_scope(app, "global", color_accent_hex=color_accent_hex)
    )
    out = _strip_note_actions_on_case_mismatch(app, out, targets)
    return _dedupe_actions(out)


def _action_is_note_kind(app: Any, action_id: str) -> bool:
    action = app.ctx.actions.get(action_id)
    return action is not None and getattr(action, "kind", "") == "note"


def _any_target_note_case_mismatch(app: Any, targets: list[ProjectRow]) -> bool:
    for row in targets:
        try:
            note_path = app._resolve_notes_path_for_row(row)
        except (OSError, ValueError, RuntimeError):
            continue
        try:
            if not note_path.is_file():
                continue
        except OSError:
            continue
        if existing_path_case_mismatch(note_path) is not None:
            return True
    return False


def label_plain(label: str) -> str:
    text = re.sub(r"\[[^\]]*\]", "", str(label))
    return " ".join(text.split()).strip()


def action_help_text(action_id: str, label: str, *, action_short_help: dict[str, str]) -> str:
    action = action_short_help.get(action_id)
    if action is None:
        plain = label_plain(label)
        return f"Run custom action: {plain}"
    return action


def custom_action_by_id(app: Any, cid: str) -> Action | None:
    return app.ctx.actions.get(cid)


def custom_action_context(
    app: Any,
    row: ProjectRow | None,
    *,
    base_dir: Path,
    fmt_ymd: Callable[[int], str],
    index: int = 0,
    total: int = 1,
) -> dict[str, str]:
    _ = fmt_ymd, index, total
    if row is None:
        return action_template.build_always_context(app, base_dir)
    return {
        **action_template.build_always_context(app, base_dir),
        **action_template.build_per_row_context(app, row, base_dir),
    }


def render_custom_command(template_text: str, context: dict[str, str]) -> str:
    return action_template.render_template(template_text, context)


def _run_custom_global_action(
    app: Any, action_id: str, template_text: str, base_dir: Path
) -> None:
    ctx = action_template.build_always_context(app, base_dir)
    cmd = render_custom_command(template_text, ctx)
    try:
        app._start_managed_shell_command(
            cmd,
            cwd=base_dir,
            label=f"custom global: {action_id}",
            wait=False,
            terminate_on_quit=True,
        )
        app._log(f"custom global action started: {action_id}", "info")
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        app._show_runtime_error(f"run custom action ({action_id})", exc)
    app._refresh_side()


def _run_custom_target_joined(
    app: Any,
    action_id: str,
    template_text: str,
    targets: list[ProjectRow],
    base_dir: Path,
) -> None:
    first = targets[0]
    for row in targets:
        app._mark_row_active(row.path)
    ctx = {
        **action_template.build_always_context(app, base_dir),
        **action_template.build_per_row_context(app, first, base_dir),
        **action_template.build_list_context(app, list(targets), base_dir),
    }
    cmd = render_custom_command(template_text, ctx)
    try:
        app._start_managed_shell_command(
            cmd,
            cwd=base_dir,
            label=f"custom target: {action_id}",
            wait=False,
            terminate_on_quit=True,
        )
        app._log(
            f"custom target action started: {action_id} (1/{len(targets)})",
            "info",
        )
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        app._show_runtime_error(f"run custom action ({action_id})", exc)
    app._refresh_side()


def _run_custom_target_per_row(
    app: Any,
    action_id: str,
    template_text: str,
    targets: list[ProjectRow],
    base_dir: Path,
) -> None:
    started = 0
    total = len(targets)
    shown_error = False
    for i, row in enumerate(targets, start=1):
        app._mark_row_active(row.path)
        ctx = {
            **action_template.build_always_context(app, base_dir),
            **action_template.build_per_row_context(app, row, base_dir),
        }
        cmd = render_custom_command(template_text, ctx)
        try:
            app._start_managed_shell_command(
                cmd,
                cwd=base_dir,
                label=f"custom target: {action_id} ({i}/{total})",
                wait=False,
                terminate_on_quit=True,
            )
            started += 1
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            app._log(f"custom action failed for {row.name}: {exc}", "error")
            if not shown_error:
                shown_error = True
                app._show_runtime_error(
                    f"run custom action ({action_id})", exc
                )
    app._log(
        f"custom target action started: {action_id} ({started}/{total})", "info"
    )
    app._refresh_side()


def run_custom_action(app: Any, action_id: str, *, base_dir: Path, fmt_ymd: Callable[[int], str]) -> None:
    action = custom_action_by_id(app, action_id)
    if action is None:
        app._log(f"custom action not found: {action_id}", "error")
        app._refresh_side()
        return
    list_command = str(action.list_command or "").strip()
    run_command = str(action.command or "").strip()
    if list_command and run_command:
        _run_custom_list_action(
            app,
            action_id,
            list_command=list_command,
            run_command=run_command,
            base_dir=base_dir,
            fmt_ymd=fmt_ymd,
        )
        return
    note_command = str(action.op or "") if action.kind == "note" else ""
    if note_command:
        _run_custom_note_action(app, action_id, note_command=note_command)
        return
    template_text = str(action.command or "").strip()
    if not template_text:
        app._log(f"custom action has empty command: {action_id}", "error")
        app._refresh_side()
        return
    scope = "global" if action.scope == "workspace" else "target"
    if scope == "global":
        _run_custom_global_action(app, action_id, template_text, base_dir)
        return
    targets = app._target_rows()
    if not targets:
        app._log("custom target action skipped: no target", "warn")
        app._refresh_side()
        return
    if action.multi == "per_row":
        _run_custom_target_per_row(app, action_id, template_text, targets, base_dir)
    else:
        _run_custom_target_joined(app, action_id, template_text, targets, base_dir)


def _run_custom_list_action(
    app: Any,
    action_id: str,
    *,
    list_command: str,
    run_command: str,
    base_dir: Path,
    fmt_ymd: Callable[[int], str],
) -> None:
    targets = app._target_rows()
    if not targets:
        app._log("custom list action skipped: no target", "warn")
        app._refresh_side()
        return
    items: list[tuple[str, str, ProjectRow]] = []
    multi = len(targets) > 1
    for row in targets:
        ctx = {
            **action_template.build_always_context(app, base_dir),
            **action_template.build_per_row_context(app, row, base_dir),
        }
        list_cmd = render_custom_command(list_command, ctx)
        try:
            proc = subprocess.run(
                ["sh", "-lc", list_cmd],
                cwd=str(base_dir),
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            app._show_runtime_error(f"run custom list action ({action_id})", exc)
            return
        if proc.returncode != 0:
            err = (proc.stderr or "").strip() or f"exit={proc.returncode}"
            app._log(f"custom list action failed for {row.name}: {err}", "error")
            continue
        for line in (proc.stdout or "").splitlines():
            value = line.strip()
            if not value:
                continue
            label = f"{row.name}: {value}" if multi else value
            items.append((value, label, row))
    if not items:
        app._log("custom list action produced no results", "warn")
        notifier = getattr(app, "notify", None)
        if callable(notifier):
            notifier("No files matched list action", severity="warning")
        app._refresh_side()
        return

    options: list[tuple[str, str]] = []
    choice_map: dict[str, tuple[str, ProjectRow]] = {}
    for i, (value, label, row) in enumerate(items, start=1):
        key = f"sel:{i}"
        options.append(
            (
                key,
                _render_filepicker_label(
                    app,
                    value,
                    label,
                    row,
                    multi=multi,
                    base_dir=base_dir,
                ),
            )
        )
        choice_map[key] = (value, row)

    app.push_screen(
        app._fuzzy_choice_screen_cls(
            "Pick file",
            options,
        ),
        lambda selected_key: _on_pick_custom_list_selection(
            app,
            selected_key,
            choice_map=choice_map,
            run_command=run_command,
            base_dir=base_dir,
            fmt_ymd=fmt_ymd,
            action_id=action_id,
        ),
    )


def _on_pick_custom_list_selection(
    app: Any,
    selected_key: str | None,
    *,
    choice_map: dict[str, tuple[str, ProjectRow]],
    run_command: str,
    base_dir: Path,
    fmt_ymd: Callable[[int], str],
    action_id: str,
) -> None:
    if not selected_key:
        app._log("custom list action cancelled", "warn")
        app._refresh_side()
        return
    selected = choice_map.get(selected_key)
    if selected is None:
        app._log("custom list action selection invalid", "error")
        app._refresh_side()
        return
    selection_value, row = selected
    app._mark_row_active(row.path)
    ctx = {
        **action_template.build_always_context(app, base_dir),
        **action_template.build_per_row_context(app, row, base_dir),
        **action_template.build_filepicker_context(selection_value),
    }
    cmd = render_custom_command(run_command, ctx)
    try:
        app._start_managed_shell_command(
            cmd,
            cwd=base_dir,
            label=f"custom list: {action_id}",
            wait=False,
            terminate_on_quit=True,
        )
        app._log(f"custom list action started: {action_id}", "info")
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        app._show_runtime_error(f"run custom list action ({action_id})", exc)
    app._refresh_side()


def _render_filepicker_label(
    app: Any,
    value: str,
    fallback_label: str,
    row: ProjectRow,
    *,
    multi: bool,
    base_dir: Path,
) -> str:
    prefix_path = base_dir if multi else row.path
    prefix = str(prefix_path)
    if not prefix.endswith("/"):
        prefix += "/"
    if value.startswith(prefix):
        suffix = value[len(prefix) :]
        return f"[dim]{app._esc(prefix)}[/]{app._esc(suffix)}"
    return f"[white]{app._esc(fallback_label)}[/]"


def _format_log_timestamp(timestamp_format: str) -> str:
    fmt = str(timestamp_format or "").strip()
    now = datetime.now().astimezone()
    if not fmt or fmt == "iso-seconds":
        return now.isoformat(timespec="seconds")
    return now.strftime(fmt)


def _notify_skip(app: Any, row: ProjectRow, reason: str) -> None:
    app._log(f"add_log skipped {row.name}: {reason}", "warn")
    notifier = getattr(app, "notify", None)
    if callable(notifier):
        notifier(f"Skipped {row.name}: {reason}", severity="warning")


def _heading_text(level: int, title: str) -> str:
    return f"{'#' * max(1, min(6, int(level)))} {title}"


def _heading_level(line: str) -> int:
    """Return the Markdown heading level for ``line`` (0 if not a heading)."""
    ls = line.lstrip()
    if not ls.startswith("#"):
        return 0
    level = 0
    for ch in ls:
        if ch == "#":
            level += 1
        else:
            break
    if level > 0 and len(ls) > level and ls[level] == " ":
        return level
    return 0


def _find_section_idx(lines: list[str], section_heading: str) -> int:
    for i, line in enumerate(lines):
        if line.strip() == section_heading:
            return i
    return -1


def _find_section_end(lines: list[str], start: int, section_level: int) -> int:
    for i in range(start, len(lines)):
        level = _heading_level(lines[i])
        if 0 < level <= section_level:
            return i
    return len(lines)


def _collect_entries(
    lines: list[str], section_idx: int, end_idx: int, entry_level: int
) -> list[tuple[str, list[str]]]:
    entries: list[tuple[str, list[str]]] = []
    i = section_idx + 1
    while i < end_idx:
        if _heading_level(lines[i]) != entry_level:
            i += 1
            continue
        ls = lines[i].lstrip()
        heading = ls[entry_level + 1 :].strip()
        body: list[str] = []
        i += 1
        while i < end_idx:
            if _heading_level(lines[i]) == entry_level:
                break
            body.append(lines[i])
            i += 1
        entries.append((heading, body))
    return entries


def _extract_log_preview(content: str, *, section_title: str, section_level: int) -> tuple[str, list[str]]:
    lines = content.splitlines()
    section_heading = _heading_text(section_level, section_title)
    section_idx = _find_section_idx(lines, section_heading)
    if section_idx < 0:
        return "(no log section yet)", []
    end_idx = _find_section_end(lines, section_idx + 1, section_level)
    entry_level = min(6, section_level + 1)
    entries = _collect_entries(lines, section_idx, end_idx, entry_level)
    if not entries:
        return "(log section exists, no entries)", []
    last_heading, last_body = entries[-1]
    body_preview = " ".join(line.strip() for line in last_body if line.strip())
    if len(body_preview) > 180:
        body_preview = body_preview[:180] + "..."
    latest = f"{last_heading} - {body_preview or '(empty)'}"
    older = [h for h, _ in entries[:-1]]
    return latest, older


def _build_log_dialog_side_info(
    valid: list[tuple[ProjectRow, Path, str | None]],
    *,
    section_title: str,
    section_level: int,
    timestamp_format: str,
) -> str:
    section_heading = _heading_text(section_level, section_title)
    entry_heading = _heading_text(min(6, section_level + 1), "<timestamp>")
    lines: list[str] = [
        f"section: {section_heading}",
        f"entry: {entry_heading}",
        f"timestamp: {timestamp_format}",
        f"targets: {len(valid)}",
        "",
    ]
    row, path, existing = valid[0]
    lines.append(f"preview file: {path.name}")
    latest, older = _extract_log_preview(existing or "", section_title=section_title, section_level=section_level)
    lines.append(f"latest: {latest}")
    if older:
        lines.append("older:")
        for heading in older[-6:]:
            lines.append(f"- {heading}")
    else:
        lines.append("older: (none)")
    if len(valid) > 1:
        lines.append("")
        lines.append(f"+{len(valid) - 1} more target(s)")
    return "\n".join(lines)


def _validate_existing_note(
    app: Any, row: ProjectRow, note_path: Path
) -> str | None | str:
    """Return the existing note text on success, None if file does not exist,
    or the sentinel string ``_NOTE_INVALID`` when the file is unusable."""
    try:
        if not note_path.is_file():
            _notify_skip(app, row, "note path is not a regular file")
            return _NOTE_INVALID
    except OSError as exc:
        _notify_skip(app, row, f"stat failed: {exc}")
        return _NOTE_INVALID
    actual_name = existing_path_case_mismatch(note_path)
    if actual_name is not None:
        _notify_skip(
            app,
            row,
            f"note case mismatch: expected '{note_path.name}', "
            f"on-disk '{actual_name}'",
        )
        return _NOTE_INVALID
    try:
        existing = note_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _notify_skip(app, row, f"read failed: {exc}")
        return _NOTE_INVALID
    try:
        validate_note(existing)
    except NoteValidationError as exc:
        _notify_skip(app, row, f"validation failed: {exc}")
        return _NOTE_INVALID
    return existing


def _collect_valid_note_targets(
    app: Any, targets: list[ProjectRow]
) -> list[tuple[ProjectRow, Path, str | None]]:
    valid: list[tuple[ProjectRow, Path, str | None]] = []
    for row in targets:
        try:
            note_path = app._resolve_notes_path_for_row(row)
        except (OSError, ValueError, RuntimeError) as exc:
            _notify_skip(app, row, f"resolve notes path failed: {exc}")
            continue
        try:
            exists = note_path.exists()
        except OSError as exc:
            _notify_skip(app, row, f"stat failed: {exc}")
            continue
        if not exists:
            valid.append((row, note_path, None))
            continue
        result = _validate_existing_note(app, row, note_path)
        if result is _NOTE_INVALID:
            continue
        valid.append((row, note_path, result))
    return valid


_NOTE_INVALID = object()


def _run_custom_note_action(
    app: Any,
    action_id: str,
    *,
    note_command: str,
) -> None:
    if note_command != "add_log":
        app._log(
            f"custom note action has unknown note_command: {note_command}",
            "error",
        )
        app._refresh_side()
        return
    targets = app._target_rows()
    if not targets:
        app._log("custom note action skipped: no target", "warn")
        app._refresh_side()
        return

    valid = _collect_valid_note_targets(app, targets)
    if not valid:
        app._log(f"custom note action {action_id}: no valid targets", "warn")
        notifier = getattr(app, "notify", None)
        if callable(notifier):
            notifier("add_log: no valid targets", severity="warning")
        app._refresh_side()
        return

    title = (
        f"Add log to {valid[0][0].name}"
        if len(valid) == 1
        else f"Add log to {len(valid)} notes"
    )
    log_conf = app.notes_config.get("log", {}) if isinstance(app.notes_config, dict) else {}
    section_conf = log_conf.get("section", {}) if isinstance(log_conf, dict) else {}
    entry_conf = log_conf.get("entry", {}) if isinstance(log_conf, dict) else {}
    section_title = str(section_conf.get("title", "Log") or "").strip() or "Log"
    try:
        section_level = int(section_conf.get("level", 2) or 2)
    except (TypeError, ValueError):
        section_level = 2
    section_level = max(1, min(6, section_level))
    timestamp_format = str(entry_conf.get("timestamp_format", "iso-seconds") or "iso-seconds")
    side_info = _build_log_dialog_side_info(
        valid,
        section_title=section_title,
        section_level=section_level,
        timestamp_format=timestamp_format,
    )
    app.push_screen(
        MultilineInputScreen(
            title,
            placeholder="log text",
            side_info=side_info,
            heading_level=min(6, section_level + 1),
        ),
        lambda text: _on_add_log_submit(app, text, valid, action_id),
    )


def _on_add_log_submit(
    app: Any,
    text: str | None,
    valid: list[tuple[ProjectRow, Path, str | None]],
    action_id: str,
) -> None:
    if text is None:
        app._log(f"custom note action cancelled: {action_id}", "warn")
        app._refresh_side()
        return
    body = str(text).rstrip("\r\n")
    if not body.strip():
        app._log(f"custom note action skipped: empty text ({action_id})", "warn")
        app._refresh_side()
        return
    log_conf = app.notes_config.get("log", {}) if isinstance(app.notes_config, dict) else {}
    section_conf = log_conf.get("section", {}) if isinstance(log_conf, dict) else {}
    entry_conf = log_conf.get("entry", {}) if isinstance(log_conf, dict) else {}
    section_title = str(section_conf.get("title", "Log") or "").strip() or "Log"
    try:
        section_level = int(section_conf.get("level", 2) or 2)
    except (TypeError, ValueError):
        section_level = 2
    section_level = max(1, min(6, section_level))
    timestamp_format = str(entry_conf.get("timestamp_format", "iso-seconds") or "iso-seconds")
    timestamp = _format_log_timestamp(timestamp_format)
    log_conf = app.notes_config.get("log", {}) if isinstance(app.notes_config, dict) else {}
    written = 0
    failed = 0
    for row, note_path, existing in valid:
        try:
            new_content = insert_log_entry(
                existing,
                project_name=row.name,
                timestamp=timestamp,
                text=body,
                section_title=section_title,
                section_level=section_level,
            )
        except NoteValidationError as exc:
            _notify_skip(app, row, f"validation failed: {exc}")
            failed += 1
            continue
        try:
            note_path.parent.mkdir(parents=True, exist_ok=True)
            note_path.write_text(new_content, encoding="utf-8")
            app._mark_row_active(row.path)
            written += 1
        except OSError as exc:
            app._show_runtime_error(f"write note ({row.name})", exc)
            failed += 1
    summary = f"add_log {action_id}: {written} written, {failed} failed/skipped"
    app._log(summary, "info" if failed == 0 else "warn")
    notifier = getattr(app, "notify", None)
    if callable(notifier) and written > 0:
        notifier(f"add_log: wrote {written} note(s)")
    app._refresh_side()
