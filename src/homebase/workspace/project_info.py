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


def _esc(value: object) -> str:
    return str(value).replace("[", "\\[")


def _clean(value: object) -> str:
    text = str(value).strip()
    return "" if text in {"-", "?"} else text


def _style_age_units(age: str, color_age_unit_hex: str) -> str:
    tokens = re.findall(r"-?\d+[a-zA-Z]", age)
    if not tokens:
        return f"[white]{age}[/]"
    return " ".join(
        f"[white]{tok[:-1]}[/][{color_age_unit_hex}]{tok[-1]}[/]" for tok in tokens
    )


def _basic_lines(row: Any, wip_hotkey: int | None) -> list[str]:
    lines = [
        f"[bold white]{_esc(row.name)}[/]",
        f"[dim]{_esc(row.path)}[/]",
        f"[cyan]archived[/]: {'[green]yes[/]' if row.archived else '[dim]no[/]'}",
    ]
    if row.wip:
        hotkey_text = f" [dim](alt+{wip_hotkey})[/]" if wip_hotkey else ""
        lines.append(f"[cyan]wip[/]: [green]yes[/]{hotkey_text}")
    else:
        lines.append("[cyan]wip[/]: [dim]no[/]")
    lines.append(f"[cyan]suffix[/]: [yellow]{_esc(_clean(row.suffix or ''))}[/]")
    return lines


def _timestamp_lines(
    row: Any,
    *,
    now_ts: int,
    color_age_unit_hex: str,
    fmt_iso: Callable[[int], str],
    fmt_age_short: Callable[[int, int | None], str],
) -> list[str]:
    created_iso = fmt_iso(row.created_ts) if row.created_ts > 0 else ""
    opened_iso = fmt_iso(row.opened_ts) if row.opened_ts > 0 else ""
    last_iso = fmt_iso(row.last_ts) if row.last_ts > 0 else ""
    created_age = _style_age_units(
        fmt_age_short(row.created_ts, now_ts), color_age_unit_hex
    )
    opened_age = _style_age_units(
        fmt_age_short(row.opened_ts, now_ts), color_age_unit_hex
    )
    last_age = _style_age_units(
        fmt_age_short(row.last_ts, now_ts), color_age_unit_hex
    )
    lines = [
        f"[cyan]created[/]: {_esc(created_iso)} [dim]([/]{created_age}[dim])[/]",
    ]
    if row.opened_ts > 0:
        lines.append(
            f"[cyan]last opened[/]: {_esc(opened_iso)} [dim]([/]{opened_age}[dim])[/]"
        )
    else:
        lines.append("[cyan]last opened[/]: ")
    lines.append(
        f"[cyan]last modified[/]: {_esc(last_iso)} "
        f"[dim]([/]{last_age}[dim], {_esc(row.src)})[/]"
    )
    return lines


def _worktree_lines(
    row: Any, load_base_data: Callable[[Any], dict[str, object]]
) -> list[str]:
    if not row.worktree_of:
        return []
    lines = [f"[cyan]worktree of[/]: [magenta]{_esc(row.worktree_of)}[/]"]
    wt_block = _read_worktree_block(load_base_data, row.path)
    if wt_block is None:
        return lines
    parent_repo = str(wt_block.get("parent_path", "")).strip()
    wt_branch = str(wt_block.get("branch", "")).strip()
    gitdir_id = str(wt_block.get("gitdir_id", "")).strip()
    if wt_branch:
        lines.append(f"[cyan]worktree branch[/]: [green]{_esc(wt_branch)}[/]")
    if parent_repo:
        lines.append(f"[cyan]parent repo[/]: [dim]{_esc(parent_repo)}[/]")
    if gitdir_id:
        lines.append(
            f"[cyan]parent admin[/]: [dim]{_esc(parent_repo)}"
            f"/.git/worktrees/{_esc(gitdir_id)}/[/]"
        )
    return lines


def _git_lines(
    row: Any, load_base_data: Callable[[Any], dict[str, object]]
) -> list[str]:
    branch = _clean(row.branch)
    dirty_mark = "[yellow]*[/]" if row.dirty == "*" else ""
    lines = [f"[cyan]git[/]: [green]{_esc(branch)}[/]{dirty_mark}"]
    if row.repo_dir:
        repo_loc = row.path / row.repo_dir
        suffix = (
            " [dim](repo_dir='.', .git at project root)[/]"
            if row.repo_dir == "."
            else ""
        )
        lines.append(f"[cyan]repo path[/]: [dim]{_esc(repo_loc)}[/]{suffix}")
    lines.extend(_worktree_lines(row, load_base_data))
    return lines


def _cache_lines(
    row: Any,
    *,
    now_ts: int,
    color_age_unit_hex: str,
    fmt_iso: Callable[[int], str],
    fmt_age_short: Callable[[int, int | None], str],
) -> list[str]:
    lines = [
        f"[cyan]cache stale[/]: {'[yellow]yes[/]' if row.stale else '[green]no[/]'} "
        f"[dim](age={row.cache_age_s}s)[/]"
    ]
    if row.last_cached_ts > 0:
        age = _style_age_units(
            fmt_age_short(row.last_cached_ts, now_ts), color_age_unit_hex
        )
        lines.append(
            f"[cyan]last cached[/]: {_esc(fmt_iso(row.last_cached_ts))} "
            f"[dim]([/]{age}[dim])[/]"
        )
    else:
        lines.append("[cyan]last cached[/]: -")
    if row.last_reconciled_ts > 0:
        age = _style_age_units(
            fmt_age_short(row.last_reconciled_ts, now_ts), color_age_unit_hex
        )
        lines.append(
            f"[cyan]last reconciled[/]: {_esc(fmt_iso(row.last_reconciled_ts))} "
            f"[dim]([/]{age}[dim])[/]"
        )
    else:
        lines.append("[cyan]last reconciled[/]: -")
    return lines


def _tags_props_lines(
    row: Any, property_display_lines: Callable[[list[str]], list[str]]
) -> list[str]:
    lines: list[str] = []
    if row.tags:
        lines.append(f"[cyan]tags[/]: {_esc(', '.join(row.tags))}")
    else:
        lines.append("[cyan]tags[/]: ")
    props = property_display_lines(row.properties)
    if props:
        lines.append("[cyan]properties[/]:")
        lines.extend([f"  [magenta]-[/] {p}" for p in props])
    else:
        lines.append("[cyan]properties[/]: ")
    return lines


def _meta_issue_fix_lines(
    code: str, base_marker_file: str, legacy_base_marker_file: str
) -> list[str]:
    if code in {"legacy_only", "legacy_conflict"}:
        return [
            f"    [magenta]fix[/]: merge metadata into {base_marker_file} "
            f"and remove {legacy_base_marker_file}",
            "    [magenta]auto-fix[/]: no",
        ]
    if code == "missing_meta":
        return [
            f"    [magenta]fix[/]: create {base_marker_file} (empty file is valid)",
            "    [magenta]auto-fix[/]: no",
        ]
    if code == "invalid_yaml":
        return [
            "    [magenta]fix[/]: correct YAML syntax so file parses",
            "    [magenta]auto-fix[/]: no (Actions -> open meta file)",
        ]
    if code == "invalid_root":
        return [
            "    [magenta]fix[/]: use mapping root (key: value), not list/scalar",
            "    [magenta]auto-fix[/]: no (Actions -> open meta file)",
        ]
    if code == "schema_warn":
        return [
            f"    [magenta]fix[/]: adjust types/unknown keys in {base_marker_file}",
            "    [magenta]auto-fix[/]: no",
        ]
    return ["    [magenta]auto-fix[/]: no"]


def _live_health_lines(
    row: Any,
    *,
    base_marker_file: str,
    legacy_base_marker_file: str,
    base_meta_issues: Callable[[Any], list[tuple[str, str, str]]],
) -> list[str]:
    issues = base_meta_issues(row.path)
    if not issues:
        return []
    lines = ["[cyan]health issues[/]:"]
    for level, code, message in issues:
        level_label = (
            "[red]ERROR[/]" if level == "error" else "[yellow]WARNING[/]"
        )
        lines.append(
            f"  {level_label} [dim]({_esc(code)})[/]: {_esc(message)}"
        )
        lines.extend(
            _meta_issue_fix_lines(code, base_marker_file, legacy_base_marker_file)
        )
    return lines


def _cached_health_lines(
    row: Any, cached_meta_health: tuple[str, str] | None
) -> list[str]:
    cached_level = ""
    cached_msg = ""
    if cached_meta_health is not None:
        cached_level = str(cached_meta_health[0]).strip().lower()
        cached_msg = str(cached_meta_health[1]).strip()
    if cached_level in {"warning", "error"} and cached_msg:
        label = "[red]ERROR[/]" if cached_level == "error" else "[yellow]WARNING[/]"
        lines = ["[cyan]health issues[/]:"]
        for part in [p.strip() for p in cached_msg.split(";") if p.strip()]:
            lines.append(f"  {label}: {_esc(part)}")
        return lines
    if "err" in row.properties or "warn" in row.properties:
        return ["[cyan]health issues[/]: [dim]flagged; details loading...[/]"]
    return []


def _last_commit_line(row: Any, run_out: Callable[..., str]) -> str:
    repo_path = (row.path / row.repo_dir) if row.repo_dir else None
    if repo_path is None or not (repo_path / ".git").exists():
        return "[cyan]last commit[/]: "
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
    return f"[cyan]last commit[/]: {_esc(_clean(last_msg or ''))}"


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
    now_ts = int(time.time())
    lines: list[str] = []
    lines.extend(_basic_lines(row, wip_hotkey))
    lines.extend(
        _timestamp_lines(
            row,
            now_ts=now_ts,
            color_age_unit_hex=color_age_unit_hex,
            fmt_iso=fmt_iso,
            fmt_age_short=fmt_age_short,
        )
    )
    lines.extend(_git_lines(row, load_base_data))
    lines.extend(
        _cache_lines(
            row,
            now_ts=now_ts,
            color_age_unit_hex=color_age_unit_hex,
            fmt_iso=fmt_iso,
            fmt_age_short=fmt_age_short,
        )
    )
    lines.extend(_tags_props_lines(row, property_display_lines))

    if include_meta_checks:
        lines.extend(
            _live_health_lines(
                row,
                base_marker_file=base_marker_file,
                legacy_base_marker_file=legacy_base_marker_file,
                base_meta_issues=base_meta_issues,
            )
        )
    else:
        lines.extend(_cached_health_lines(row, cached_meta_health))

    lines.append(f"[cyan]description[/]: {_esc(row.description or '')}")

    if include_meta_checks:
        data = load_base_data(row.path)
        keys = ", ".join(sorted(data.keys())) if data else ""
        lines.append(f"[cyan]{base_marker_file} keys[/]: {_esc(keys)}")

    lines.append(_last_commit_line(row, run_out))
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
