from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from string import Template
from typing import Any, Callable

from ...core.models import ProjectRow


def custom_actions_for_scope(
    app: Any,
    scope: str,
    *,
    color_accent_hex: str,
) -> list[tuple[str, str]]:
    normal: list[tuple[str, str]] = []
    list_actions: list[tuple[str, str]] = []
    for act in app.custom_actions:
        if str(act.get("scope", "target")) != scope:
            continue
        cid = str(act.get("id", "")).strip()
        label = str(act.get("label", cid)).strip() or cid
        is_list_action = bool(
            str(act.get("list_command", "")).strip()
            and str(act.get("run_command", "")).strip()
        )
        if is_list_action:
            plain_label = app._esc(label)
            rendered_label = f"[#40E0D0]{plain_label}[/] [dim](filepicker)[/]"
        else:
            rendered_label = f"[{color_accent_hex}]{app._esc(label)}[/]"
        target = (
            f"custom:{cid}",
            rendered_label,
        )
        if is_list_action:
            list_actions.append(target)
        else:
            normal.append(target)
    return normal + list_actions


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

    if targets:
        out.append(("tags_set", "[white]Tags...[/]"))
        out.append(("reconcile_selection_cache", "[white]Reconcile target cache now[/]"))
        if app.view_mode == "active":
            out.append(("suffix_set", "[white]Suffix...[/]"))

        for key, label in app.view_config[app.view_mode]["actions"]:
            if key in {"archive", "restore", "pack", "unpack", "toggle_pack", "delete"}:
                runnable, _skipped = app._preflight_bulk_action(key, [r.path for r in targets])
                if not runnable:
                    continue
            out.append((key, f"[white]{label}[/]"))

    if targets:
        out.append(("rename_item", "[white]Rename item...[/]"))
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
            out.append(("review_meta", "[white]Open .base.yaml and review warnings[/]"))
        if has_legacy_meta:
            out.append(("rename_meta_ext", "[white]Rename .base.yml -> .base.yaml[/]"))

    out.extend(
        [
            ("refresh_cache", "[white]Refresh cache[/]"),
            ("full_reconcile", "[white]Full reconcile (force rescan)[/]"),
            ("reload_global_config", "[white]Reload global config[/]"),
            ("edit_global_config", "[white]Edit global config in $EDITOR[/]"),
        ]
    )
    if app.active_rows or app.archived_rows:
        out.append(("reconcile_all_cache", "[white]Reconcile all cached rows now[/]"))

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
    template_text = str(act.get("command", "")).strip()
    if not template_text:
        app._log(f"custom action has empty command: {action_id}", "error")
        app._refresh_side()
        return

    if scope == "global":
        ctx = custom_action_context(app, None, base_dir=base_dir, fmt_ymd=fmt_ymd, index=1, total=1)
        cmd = render_custom_command(template_text, ctx)
        try:
            subprocess.Popen(["sh", "-lc", cmd], cwd=str(base_dir))
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
            subprocess.Popen(["sh", "-lc", cmd], cwd=str(base_dir))
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
            subprocess.Popen(["sh", "-lc", cmd], cwd=str(base_dir))
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
    ctx = custom_action_context(app, row, base_dir=base_dir, fmt_ymd=fmt_ymd, index=1, total=1)
    ctx["selection"] = selection_value
    ctx["selection_q"] = shlex.quote(selection_value)
    cmd = render_custom_command(run_command, ctx)
    try:
        subprocess.Popen(["sh", "-lc", cmd], cwd=str(base_dir))
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
