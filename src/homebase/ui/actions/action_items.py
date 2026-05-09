from __future__ import annotations

import re
import shlex
import subprocess
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any, Callable

from ...core.constants import BUILTIN_ACTIONS
from ...core.models import ProjectRow
from ...notes.log_md import NoteValidationError, insert_log_entry, validate_note
from ..screens.multiline_input import MultilineInputScreen


def custom_actions_for_scope(
    app: Any,
    scope: str,
    *,
    color_accent_hex: str,
) -> list[tuple[str, str]]:
    normal: list[tuple[str, str]] = []
    list_actions: list[tuple[str, str]] = []
    note_actions: list[tuple[str, str]] = []
    for act in app.custom_actions:
        if str(act.get("scope", "target")) != scope:
            continue
        cid = str(act.get("id", "")).strip()
        label = str(act.get("label", cid)).strip() or cid
        is_list_action = bool(
            str(act.get("list_command", "")).strip()
            and str(act.get("run_command", "")).strip()
        )
        is_note_action = bool(str(act.get("note_command", "")).strip())
        if is_note_action:
            plain_label = app._esc(label)
            rendered_label = f"[#FFB347]{plain_label}[/] [dim](note)[/]"
        elif is_list_action:
            plain_label = app._esc(label)
            rendered_label = f"[#40E0D0]{plain_label}[/] [dim](filepicker)[/]"
        else:
            rendered_label = f"[{color_accent_hex}]{app._esc(label)}[/]"
        target = (
            f"custom:{cid}",
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


def valid_action_items(
    app: Any,
    *,
    color_accent_hex: str,
    base_meta_issues: Callable[[Path], list[tuple[str, str, str]]],
) -> list[tuple[str, str]]:
    def builtin_label(action_id: str, fallback: str) -> str:
        meta = BUILTIN_ACTIONS.get(action_id)
        return meta.default_label if meta is not None else fallback

    targets = app._target_rows()
    out: list[tuple[str, str]] = []

    out.extend(app._readme_button_actions())
    out.extend(app._notes_button_actions())

    if targets:
        out.append(("tags_set", f"[white]{builtin_label('tags_set', 'Tags...')}[/]"))
        out.append(
            (
                "reconcile_selection_cache",
                f"[white]{builtin_label('reconcile_selection_cache', 'Reconcile target cache now')}[/]",
            )
        )
        if app.view_mode == "active":
            out.append(("suffix_set", f"[white]{builtin_label('suffix_set', 'Suffix...')}[/]"))

        for key, label in app.view_config[app.view_mode]["actions"]:
            if key in {"archive", "restore", "pack", "unpack", "toggle_pack", "delete"}:
                runnable, _skipped = app._preflight_bulk_action(key, [r.path for r in targets])
                if not runnable:
                    continue
            out.append((key, f"[white]{label}[/]"))

    if targets:
        out.append(("rename_item", f"[white]{builtin_label('rename_item', 'Rename item...')}[/]"))
        has_review_meta = False
        has_legacy_meta = False
        for row in targets:
            issue_codes = {code for _lvl, code, _msg in base_meta_issues(row.path)}
            if issue_codes and not row.packed:
                has_review_meta = True
            if (
                ("legacy_only" in issue_codes or "legacy_conflict" in issue_codes)
                and not row.packed
            ):
                has_legacy_meta = True
        if has_review_meta:
            out.append(
                (
                    "review_meta",
                    f"[white]{builtin_label('review_meta', 'Open .base.yaml and review warnings')}[/]",
                )
            )
        if has_legacy_meta:
            out.append(
                (
                    "rename_meta_ext",
                    f"[white]{builtin_label('rename_meta_ext', 'Rename .base.yml -> .base.yaml')}[/]",
                )
            )

    out.extend(
        [
            ("refresh_cache", f"[white]{builtin_label('refresh_cache', 'Refresh cache')}[/]"),
            (
                "full_reconcile",
                f"[white]{builtin_label('full_reconcile', 'Full reconcile (force rescan)')}[/]",
            ),
            (
                "reload_global_config",
                f"[white]{builtin_label('reload_global_config', 'Reload global config')}[/]",
            ),
            (
                "edit_global_config",
                f"[white]{builtin_label('edit_global_config', 'Edit global config in $EDITOR')}[/]",
            ),
        ]
    )
    if app.active_rows or app.archived_rows:
        out.append(
            (
                "reconcile_all_cache",
                f"[white]{builtin_label('reconcile_all_cache', 'Reconcile all cached rows now')}[/]",
            )
        )

    if targets:
        out.extend(custom_actions_for_scope(app, "target", color_accent_hex=color_accent_hex))
    out.extend(
        custom_actions_for_scope(
            app,
            "global",
            color_accent_hex=color_accent_hex,
        )
    )

    uniq: list[tuple[str, str]] = []
    seen: set[str] = set()
    for aid, label in out:
        if aid in seen:
            continue
        seen.add(aid)
        uniq.append((aid, label))
    return uniq


def label_plain(label: str) -> str:
    text = re.sub(r"\[[^\]]*\]", "", str(label))
    return " ".join(text.split()).strip()


def action_help_text(action_id: str, label: str, *, action_short_help: dict[str, str]) -> str:
    if action_id.startswith("custom:"):
        plain = label_plain(label)
        return f"Run custom action: {plain}"
    return action_short_help.get(action_id, label_plain(label))


def custom_action_by_id(app: Any, cid: str) -> dict[str, str] | None:
    for act in app.custom_actions:
        if str(act.get("id", "")).strip() == cid:
            return act
    return None


def custom_action_context(
    app: Any,
    row: ProjectRow | None,
    *,
    base_dir: Path,
    fmt_ymd: Callable[[int], str],
    index: int = 0,
    total: int = 1,
) -> dict[str, str]:
    ctx: dict[str, str] = {
        "base_dir": str(base_dir),
        "view_mode": app.view_mode,
        "selection_index": str(index),
        "selection_count": str(total),
    }
    if row is None:
        return ctx
    rel = row.path
    try:
        rel = row.path.relative_to(base_dir)
    except ValueError:
        pass
    ctx.update(
        {
            "full_path": str(row.path),
            "rel_path": str(rel),
            "name": row.name,
            "parent_path": str(row.path.parent),
            "tags": ",".join(row.tags),
            "properties": ",".join(row.properties),
            "created": row.created,
            "last_modified": row.last,
            "last_opened": fmt_ymd(row.opened_ts) if row.opened_ts > 0 else "",
            "branch": row.branch,
        }
    )
    return ctx


def render_custom_command(template_text: str, context: dict[str, str]) -> str:
    converted = re.sub(
        r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}",
        lambda m: "${" + m.group(1) + "}",
        template_text,
    )
    return Template(converted).safe_substitute(context)


def run_custom_action(app: Any, action_id: str, *, base_dir: Path, fmt_ymd: Callable[[int], str]) -> None:
    act = custom_action_by_id(app, action_id)
    if act is None:
        app._log(f"custom action not found: {action_id}", "error")
        app._refresh_side()
        return
    scope = str(act.get("scope", "target"))
    menu_action = str(act.get("action", "")).strip()
    if menu_action:
        app._on_pick_actions(menu_action)
        return
    list_command = str(act.get("list_command", "")).strip()
    run_command = str(act.get("run_command", "")).strip()
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
    note_command = str(act.get("note_command", "")).strip()
    if note_command:
        _run_custom_note_action(
            app,
            action_id,
            note_command=note_command,
        )
        return
    template_text = str(act.get("command", "")).strip()
    if not template_text:
        app._log(f"custom action has empty command: {action_id}", "error")
        app._refresh_side()
        return

    if scope == "global":
        ctx = custom_action_context(app, None, base_dir=base_dir, fmt_ymd=fmt_ymd, index=1, total=1)
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
        return

    targets = app._target_rows()
    if not targets:
        app._log("custom target action skipped: no target", "warn")
        app._refresh_side()
        return
    loop_on_multi = str(act.get("loop_on_multi", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not loop_on_multi:
        first = targets[0]
        for row in targets:
            app._mark_row_active(row.path)
        ctx = custom_action_context(
            app,
            first,
            base_dir=base_dir,
            fmt_ymd=fmt_ymd,
            index=1,
            total=len(targets),
        )
        ctx["full_path"] = " ".join(_double_quoted(str(row.path)) for row in targets)
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
        return
    started = 0
    total = len(targets)
    shown_error = False
    for i, row in enumerate(targets, start=1):
        app._mark_row_active(row.path)
        ctx = custom_action_context(
            app,
            row,
            base_dir=base_dir,
            fmt_ymd=fmt_ymd,
            index=i,
            total=total,
        )
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
                app._show_runtime_error(f"run custom action ({action_id})", exc)
    app._log(f"custom target action started: {action_id} ({started}/{total})", "info")
    app._refresh_side()


def _double_quoted(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


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
        ctx = custom_action_context(app, row, base_dir=base_dir, fmt_ymd=fmt_ymd, index=1, total=1)
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
    ctx = custom_action_context(app, row, base_dir=base_dir, fmt_ymd=fmt_ymd, index=1, total=1)
    ctx["selection"] = selection_value
    ctx["selection_q"] = shlex.quote(selection_value)
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


def _local_iso_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _notify_skip(app: Any, row: ProjectRow, reason: str) -> None:
    app._log(f"add_log skipped {row.name}: {reason}", "warn")
    notifier = getattr(app, "notify", None)
    if callable(notifier):
        notifier(f"Skipped {row.name}: {reason}", severity="warning")


def _run_custom_note_action(
    app: Any,
    action_id: str,
    *,
    note_command: str,
) -> None:
    if note_command != "add_log":
        app._log(
            f"custom note action has unknown note_command: {note_command}", "error"
        )
        app._refresh_side()
        return
    targets = app._target_rows()
    if not targets:
        app._log("custom note action skipped: no target", "warn")
        app._refresh_side()
        return

    valid: list[tuple[ProjectRow, Path, str | None]] = []
    for row in targets:
        try:
            note_path = app._resolve_notes_path_for_row(row)
        except (OSError, ValueError, RuntimeError) as exc:
            _notify_skip(app, row, f"resolve notes path failed: {exc}")
            continue
        existing: str | None = None
        try:
            exists = note_path.exists()
        except OSError as exc:
            _notify_skip(app, row, f"stat failed: {exc}")
            continue
        if exists:
            try:
                if not note_path.is_file():
                    _notify_skip(app, row, "note path is not a regular file")
                    continue
            except OSError as exc:
                _notify_skip(app, row, f"stat failed: {exc}")
                continue
            try:
                existing = note_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                _notify_skip(app, row, f"read failed: {exc}")
                continue
            try:
                validate_note(existing)
            except NoteValidationError as exc:
                _notify_skip(app, row, f"validation failed: {exc}")
                continue
        valid.append((row, note_path, existing))

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
    app.push_screen(
        MultilineInputScreen(title, placeholder="log text"),
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
    timestamp = _local_iso_timestamp()
    written = 0
    failed = 0
    for row, note_path, existing in valid:
        try:
            new_content = insert_log_entry(
                existing,
                project_name=row.name,
                timestamp=timestamp,
                text=body,
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
