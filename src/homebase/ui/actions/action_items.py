from __future__ import annotations

import re
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
    out: list[tuple[str, str]] = []
    for act in app.custom_actions:
        if str(act.get("scope", "")) != scope:
            continue
        cid = str(act.get("id", "")).strip()
        label = str(act.get("label", cid)).strip() or cid
        out.append(
            (
                f"custom:{cid}",
                f"[{color_accent_hex}]{app._esc(label)}[/] [dim](custom)[/]",
            )
        )
    return out


def valid_action_items(
    app: Any,
    *,
    color_accent_hex: str,
    base_meta_issues: Callable[[Path], list[tuple[str, str, str]]],
) -> list[tuple[str, str]]:
    targets = app._target_rows()
    selected = app._selected_row()
    out: list[tuple[str, str]] = []

    out.extend(app._readme_button_actions())
    out.extend(app._notes_button_actions())

    if targets:
        out.append(("tags_set", "[white]Tags...[/]"))
        out.append(("reconcile_selection_cache", "[white]Reconcile selected cache now[/]"))
        if app.view_mode == "active":
            out.append(("suffix_set", "[white]Suffix...[/]"))

        for key, label in app.view_config[app.view_mode]["actions"]:
            if key in {"archive", "restore", "pack", "unpack", "toggle_pack", "delete"}:
                runnable, _skipped = app._preflight_bulk_action(key, [r.path for r in targets])
                if not runnable:
                    continue
            out.append((key, f"[white]{label}[/]"))

    if selected is not None:
        out.append(("rename_item", "[white]Rename item...[/]"))
        issue_codes = {code for _lvl, code, _msg in base_meta_issues(selected.path)}
        if issue_codes and not selected.packed:
            out.append(("review_meta", "[white]Open .base.yml and review warnings[/]"))
        if ("legacy_only" in issue_codes or "legacy_conflict" in issue_codes) and not selected.packed:
            out.append(("rename_meta_ext", "[white]Rename .base.yaml -> .base.yml[/]"))

    out.extend(
        [
            ("refresh_cache", "[white]Refresh cache[/]"),
            ("full_reconcile", "[white]Full reconcile (force rescan)[/]"),
        ]
    )
    if app.active_rows or app.archived_rows:
        out.append(("reconcile_all_cache", "[white]Reconcile all cached rows now[/]"))

    if targets:
        out.extend(custom_actions_for_scope(app, "selection", color_accent_hex=color_accent_hex))
    if selected is not None:
        out.extend(custom_actions_for_scope(app, "item", color_accent_hex=color_accent_hex))
    out.extend(custom_actions_for_scope(app, "global", color_accent_hex=color_accent_hex))

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
    scope = str(act.get("scope", "item"))
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

    if scope == "item":
        row = app._selected_row()
        if row is None:
            app._log("custom item action skipped: no focused item", "warn")
            app._refresh_side()
            return
        ctx = custom_action_context(app, row, base_dir=base_dir, fmt_ymd=fmt_ymd, index=1, total=1)
        cmd = render_custom_command(template_text, ctx)
        try:
            subprocess.Popen(["sh", "-lc", cmd], cwd=str(base_dir))
            app._log(f"custom item action started: {action_id} ({row.name})", "info")
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            app._show_runtime_error(f"run custom action ({action_id})", exc)
        app._refresh_side()
        return

    targets = app._target_rows()
    if not targets:
        app._log("custom selection action skipped: no selection", "warn")
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
    app._log(f"custom selection action started: {action_id} ({started}/{total})", "info")
    app._refresh_side()
