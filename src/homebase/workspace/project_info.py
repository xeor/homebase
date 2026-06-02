from __future__ import annotations

import re
import subprocess
import time
from typing import Any, Callable


def _read_worktree_block(
    load_base_data: Callable[[Any], dict[str, object]],
    path: Any,
) -> dict[str, object] | None:
    try:
        data = load_base_data(path)
    except (OSError, ValueError):
        return None
    raw = data.get("worktree") if isinstance(data, dict) else None
    return raw if isinstance(raw, dict) else None


def build_project_info_text(
    row: Any,
    *,
    base_marker_file: str,
    legacy_base_marker_file: str,
    color_age_unit_hex: str,
    wip_hotkey: int | None,
    include_meta_checks: bool,
    fmt_iso: Callable[[int], str],
    fmt_age_short: Callable[[int, int | None], str],
    property_display_lines: Callable[[list[str]], list[str]],
    base_meta_issues: Callable[[Any], list[tuple[str, str, str]]],
    load_base_data: Callable[[Any], dict[str, object]],
    run_out: Callable[..., str],
    cached_meta_health: tuple[str, str] | None = None,
) -> str:
    def esc(value: object) -> str:
        return str(value).replace("[", "\\[")

    def clean(value: object) -> str:
        text = str(value).strip()
        return "" if text in {"-", "?"} else text

    def style_age_units(age: str) -> str:
        tokens = re.findall(r"-?\d+[a-zA-Z]", age)
        if not tokens:
            return f"[white]{age}[/]"
        return " ".join(
            f"[white]{tok[:-1]}[/][{color_age_unit_hex}]{tok[-1]}[/]" for tok in tokens
        )

    now_ts = int(time.time())
    lines: list[str] = []
    lines.append(f"[bold white]{esc(row.name)}[/]")
    lines.append(f"[dim]{esc(row.path)}[/]")
    lines.append(f"[cyan]archived[/]: {'[green]yes[/]' if row.archived else '[dim]no[/]'}")
    if row.wip:
        hotkey_text = f" [dim](alt+{wip_hotkey})[/]" if wip_hotkey else ""
        lines.append(f"[cyan]wip[/]: [green]yes[/]{hotkey_text}")
    else:
        lines.append("[cyan]wip[/]: [dim]no[/]")
    lines.append(f"[cyan]suffix[/]: [yellow]{esc(clean(row.suffix or ''))}[/]")

    created_iso = fmt_iso(row.created_ts) if row.created_ts > 0 else ""
    opened_iso = fmt_iso(row.opened_ts) if row.opened_ts > 0 else ""
    last_iso = fmt_iso(row.last_ts) if row.last_ts > 0 else ""
    created_age = style_age_units(fmt_age_short(row.created_ts, now_ts))
    opened_age = style_age_units(fmt_age_short(row.opened_ts, now_ts))
    last_age = style_age_units(fmt_age_short(row.last_ts, now_ts))
    lines.append(f"[cyan]created[/]: {esc(created_iso)} [dim]([/]{created_age}[dim])[/]")
    if row.opened_ts > 0:
        lines.append(f"[cyan]last opened[/]: {esc(opened_iso)} [dim]([/]{opened_age}[dim])[/]")
    else:
        lines.append("[cyan]last opened[/]: ")
    lines.append(
        f"[cyan]last modified[/]: {esc(last_iso)} [dim]([/]{last_age}[dim], {esc(row.src)})[/]"
    )

    branch = clean(row.branch)
    dirty_mark = "[yellow]*[/]" if row.dirty == "*" else ""
    lines.append(f"[cyan]git[/]: [green]{esc(branch)}[/]{dirty_mark}")
    if row.repo_dir:
        repo_loc = row.path / row.repo_dir
        suffix = " [dim](repo_dir='.', .git at project root)[/]" if row.repo_dir == "." else ""
        lines.append(f"[cyan]repo path[/]: [dim]{esc(repo_loc)}[/]{suffix}")
    if row.worktree_of:
        lines.append(f"[cyan]worktree of[/]: [magenta]{esc(row.worktree_of)}[/]")
        wt_block = _read_worktree_block(load_base_data, row.path)
        if wt_block is not None:
            parent_repo = str(wt_block.get("parent_path", "")).strip()
            wt_branch = str(wt_block.get("branch", "")).strip()
            gitdir_id = str(wt_block.get("gitdir_id", "")).strip()
            if wt_branch:
                lines.append(f"[cyan]worktree branch[/]: [green]{esc(wt_branch)}[/]")
            if parent_repo:
                lines.append(f"[cyan]parent repo[/]: [dim]{esc(parent_repo)}[/]")
            if gitdir_id:
                lines.append(
                    f"[cyan]parent admin[/]: [dim]{esc(parent_repo)}/.git/worktrees/{esc(gitdir_id)}/[/]"
                )
    lines.append(
        f"[cyan]cache stale[/]: {'[yellow]yes[/]' if row.stale else '[green]no[/]'} [dim](age={row.cache_age_s}s)[/]"
    )

    if row.last_cached_ts > 0:
        lines.append(
            f"[cyan]last cached[/]: {esc(fmt_iso(row.last_cached_ts))} [dim]([/]{style_age_units(fmt_age_short(row.last_cached_ts, now_ts))}[dim])[/]"
        )
    else:
        lines.append("[cyan]last cached[/]: -")

    if row.last_reconciled_ts > 0:
        lines.append(
            f"[cyan]last reconciled[/]: {esc(fmt_iso(row.last_reconciled_ts))} [dim]([/]{style_age_units(fmt_age_short(row.last_reconciled_ts, now_ts))}[dim])[/]"
        )
    else:
        lines.append("[cyan]last reconciled[/]: -")

    lines.append(f"[cyan]tags[/]: {esc(', '.join(row.tags))}" if row.tags else "[cyan]tags[/]: ")
    props = property_display_lines(row.properties)
    if props:
        lines.append("[cyan]properties[/]:")
        lines.extend([f"  [magenta]-[/] {p}" for p in props])
    else:
        lines.append("[cyan]properties[/]: ")

    if include_meta_checks:
        issues = base_meta_issues(row.path)
        if issues:
            lines.append("[cyan]health issues[/]:")
            for level, code, message in issues:
                level_label = "[red]ERROR[/]" if level == "error" else "[yellow]WARNING[/]"
                lines.append(f"  {level_label} [dim]({esc(code)})[/]: {esc(message)}")
                if code in {"legacy_only", "legacy_conflict"}:
                    lines.append(
                        f"    [magenta]fix[/]: merge metadata into {base_marker_file} and remove {legacy_base_marker_file}"
                    )
                    lines.append("    [magenta]auto-fix[/]: no")
                elif code == "missing_meta":
                    lines.append(f"    [magenta]fix[/]: create {base_marker_file} (empty file is valid)")
                    lines.append("    [magenta]auto-fix[/]: no")
                elif code == "invalid_yaml":
                    lines.append("    [magenta]fix[/]: correct YAML syntax so file parses")
                    lines.append("    [magenta]auto-fix[/]: no (Actions -> open meta file)")
                elif code == "invalid_root":
                    lines.append("    [magenta]fix[/]: use mapping root (key: value), not list/scalar")
                    lines.append("    [magenta]auto-fix[/]: no (Actions -> open meta file)")
                elif code == "schema_warn":
                    lines.append(f"    [magenta]fix[/]: adjust types/unknown keys in {base_marker_file}")
                    lines.append("    [magenta]auto-fix[/]: no")
                else:
                    lines.append("    [magenta]auto-fix[/]: no")
    else:
        cached_level = ""
        cached_msg = ""
        if cached_meta_health is not None:
            cached_level = str(cached_meta_health[0]).strip().lower()
            cached_msg = str(cached_meta_health[1]).strip()
        if cached_level in {"warning", "error"} and cached_msg:
            label = "[red]ERROR[/]" if cached_level == "error" else "[yellow]WARNING[/]"
            lines.append("[cyan]health issues[/]:")
            for part in [p.strip() for p in cached_msg.split(";") if p.strip()]:
                lines.append(f"  {label}: {esc(part)}")
        elif "err" in row.properties or "warn" in row.properties:
            lines.append(
                "[cyan]health issues[/]: [dim]flagged; details loading...[/]"
            )

    lines.append(f"[cyan]description[/]: {esc(row.description or '')}")

    if include_meta_checks:
        data = load_base_data(row.path)
        keys = ", ".join(sorted(data.keys())) if data else ""
        lines.append(f"[cyan]{base_marker_file} keys[/]: {esc(keys)}")

    repo_path = (row.path / row.repo_dir) if row.repo_dir else None
    if repo_path is not None and (repo_path / ".git").exists():
        try:
            last_msg = run_out(
                "git",
                "-C",
                str(repo_path),
                "log",
                "-1",
                "--pretty=%h %ad %s",
                "--date=iso-strict",
            )
        except (subprocess.SubprocessError, OSError, ValueError):
            last_msg = "-"
        lines.append(f"[cyan]last commit[/]: {esc(clean(last_msg or ''))}")
    else:
        lines.append("[cyan]last commit[/]: ")

    return "\n".join(lines)


def project_info_text(
    row: Any,
    *,
    wip_hotkey: int | None = None,
    include_meta_checks: bool = True,
    cached_meta_health: tuple[str, str] | None = None,
) -> str:
    """Convenience wrapper that wires the workspace's metadata helpers
    into ``build_project_info_text``. Used by the UI side panels."""
    from ..core import utils as core_utils
    from ..core.constants import (
        BASE_MARKER_FILE,
        COLOR_AGE_UNIT_HEX,
        LEGACY_BASE_MARKER_FILE,
    )
    from ..metadata.api import (
        base_meta_issues,
        load_base_data,
        property_display_lines,
    )

    return build_project_info_text(
        row,
        base_marker_file=BASE_MARKER_FILE,
        legacy_base_marker_file=LEGACY_BASE_MARKER_FILE,
        color_age_unit_hex=COLOR_AGE_UNIT_HEX,
        wip_hotkey=wip_hotkey,
        include_meta_checks=include_meta_checks,
        fmt_iso=core_utils.fmt_iso,
        fmt_age_short=core_utils.fmt_age_short,
        property_display_lines=property_display_lines,
        base_meta_issues=base_meta_issues,
        load_base_data=load_base_data,
        run_out=core_utils.run_out,
        cached_meta_health=cached_meta_health,
    )
