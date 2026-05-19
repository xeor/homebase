from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ...archive import date_detect
from ...core import utils as core_utils
from ...core.constants import (
    ARCHIVE_DIR_NAME,
    ARCHIVE_TZ,
    PACKED_ARCHIVE_SUFFIX,
)
from ...core.models import ProjectRow


def _rel(path: Path, base_dir: Path, *, is_under: Callable[[Path, Path], bool]) -> str:
    if is_under(path, base_dir):
        try:
            return str(path.relative_to(base_dir))
        except ValueError:
            return str(path)
    return str(path)


def _archive_destination_preview(path: Path, base_dir: Path) -> tuple[Path, str, bool]:
    """Return ``(dest, source_label, used_fallback)``.

    Mirrors the CLI's ``_resolve_archive_date_ts`` → ``archive_destination``
    chain without printing, so the user sees exactly where each path
    lands and which signal picked the date. ``used_fallback`` is ``True``
    only when detection found nothing and we fell back to today.
    """
    stem, _ = core_utils.split_archive_name(
        path.name,
        parse_timestamp=lambda v: core_utils.parse_archive_timestamp(v, ARCHIVE_TZ),
    )
    detection = None
    if path.exists():
        detection = date_detect.detect_folder_date(
            path,
            parse_timestamp=lambda v: core_utils.parse_archive_timestamp(v, ARCHIVE_TZ),
            archive_tz=ARCHIVE_TZ,
        )
    if detection is not None:
        iso = core_utils.archive_iso_from_ts(detection.ts, ARCHIVE_TZ)
        source_label = detection.source
        used_fallback = False
    else:
        iso = core_utils.archive_now_iso(ARCHIVE_TZ)
        source_label = f"today fallback ({iso[:10]})"
        used_fallback = True
    date_prefix = iso[:10]
    year = date_prefix[:4]
    dest = base_dir / ARCHIVE_DIR_NAME / year / f"{date_prefix}_{stem}"
    return dest, source_label, used_fallback


def _packed_target(path: Path) -> Path:
    return path.with_name(f"{path.name}{PACKED_ARCHIVE_SUFFIX}")


def _unpacked_target(path: Path) -> Path:
    return path.with_name(
        core_utils.packed_archive_dir_name(path, PACKED_ARCHIVE_SUFFIX)
    )


def _row_for(app: Any, path: Path) -> ProjectRow | None:
    hit = app._find_row(path)
    if hit is None:
        return None
    rows, idx = hit
    return rows[idx]


def _truncate(text: str, limit: int = 70) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _archive_preview_line(
    app: Any, path: Path, base_dir: Path, reason: str | None,
    *, is_under: Callable[[Path, Path], bool],
) -> list[str]:
    rel = app._esc(_rel(path, base_dir, is_under=is_under))
    out: list[str] = []
    if reason:
        out.append(f"  - {rel} [yellow](skip: {app._esc(reason)})[/]")
        return out
    try:
        dest, source_label, used_fallback = _archive_destination_preview(path, base_dir)
    except OSError as exc:
        out.append(f"  - {rel} [red](preview failed: {app._esc(exc)})[/]")
        return out
    try:
        dest_rel = str(dest.relative_to(base_dir))
    except ValueError:
        dest_rel = str(dest)
    color = "yellow" if used_fallback else "dim"
    out.append(
        f"  - {rel}  [dim]→[/] {app._esc(dest_rel)}  [{color}]({app._esc(source_label)})[/]"
    )
    return out


def _delete_preview_lines(
    app: Any, path: Path, base_dir: Path, reason: str | None,
    *, is_under: Callable[[Path, Path], bool],
) -> list[str]:
    rel = app._esc(_rel(path, base_dir, is_under=is_under))
    if reason:
        return [f"  - {rel} [yellow](skip: {app._esc(reason)})[/]"]
    row = _row_for(app, path)
    badges: list[str] = []
    if row is not None:
        if row.archived:
            badges.append("[cyan]archived[/]")
        if row.packed:
            badges.append("[cyan]packed[/]")
        if row.wip:
            badges.append("[cyan]wip[/]")
        if row.size_bytes > 0:
            badges.append(f"[dim]{core_utils.fmt_size_human(row.size_bytes)}[/]")
    head = f"  - {rel}"
    if badges:
        head += "  " + " ".join(badges)
    out = [head]
    if row is not None:
        if row.tags:
            out.append(f"      [dim]tags:[/] {app._esc(', '.join(row.tags))}")
        if row.description:
            out.append(
                f"      [dim]desc:[/] {app._esc(_truncate(row.description))}"
            )
        if row.archived and row.restore_target is not None:
            out.append(
                f"      [dim]restore_target:[/] {app._esc(str(row.restore_target))}"
            )
    return out


def _restore_preview_lines(
    app: Any, path: Path, base_dir: Path, reason: str | None,
    *, is_under: Callable[[Path, Path], bool],
    archived_restore_target: Callable[[Path, Path], Path],
) -> list[str]:
    rel = app._esc(_rel(path, base_dir, is_under=is_under))
    row = _row_for(app, path)
    target: Path | None = None
    if row is not None and row.restore_target is not None:
        target = row.restore_target
    else:
        try:
            target = archived_restore_target(base_dir, path)
        except (OSError, ValueError):
            target = None
    conflict = False
    if target is not None:
        try:
            conflict = target.exists()
        except OSError:
            conflict = False
    head_parts = [f"  - {rel}"]
    if target is not None:
        try:
            tgt_rel = str(target.relative_to(base_dir))
        except ValueError:
            tgt_rel = str(target)
        head_parts.append(f"[dim]→[/] {app._esc(tgt_rel)}")
    if reason:
        head_parts.append(f"[yellow](skip: {app._esc(reason)})[/]")
    elif conflict:
        head_parts.append("[red](target exists — will prompt)[/]")
    else:
        head_parts.append("[green](ready)[/]")
    out = ["  ".join(head_parts)]
    if row is not None and row.archived_ts > 0:
        out.append(
            f"      [dim]archived:[/] {core_utils.fmt_ymd(row.archived_ts)}"
        )
    return out


def _pack_preview_lines(
    app: Any,
    path: Path,
    base_dir: Path,
    reason: str | None,
    *,
    action: str,
    is_under: Callable[[Path, Path], bool],
    is_packed_path: Callable[[Path], bool],
) -> list[str]:
    rel = app._esc(_rel(path, base_dir, is_under=is_under))
    if reason:
        return [f"  - {rel} [yellow](skip: {app._esc(reason)})[/]"]
    if action == "pack":
        result = _packed_target(path)
    elif action == "unpack":
        result = _unpacked_target(path)
    else:  # toggle_pack
        result = _unpacked_target(path) if is_packed_path(path) else _packed_target(path)
    try:
        result_rel = str(result.relative_to(base_dir))
    except ValueError:
        result_rel = str(result)
    row = _row_for(app, path)
    size_part = ""
    if row is not None and row.size_bytes > 0:
        size_part = f"  [dim]{core_utils.fmt_size_human(row.size_bytes)}[/]"
    return [
        f"  - {rel}{size_part}  [dim]→[/] {app._esc(result_rel)}"
    ]


def _generic_preview_line(
    app: Any, path: Path, base_dir: Path, reason: str | None,
    *, is_under: Callable[[Path, Path], bool],
) -> str:
    rel = app._esc(_rel(path, base_dir, is_under=is_under))
    if reason:
        return f"  - {rel} [yellow](skip: {app._esc(reason)})[/]"
    return f"  - {rel} [green](ready)[/]"


def build_bulk_confirm_payload(
    app: Any,
    action: str,
    paths: list[Path],
    *,
    base_dir: Path,
    archived_restore_target: Callable[[Path, Path], Path],
    is_under: Callable[[Path, Path], bool],
    is_packed_archive_path: Callable[[Path], bool] | None = None,
) -> tuple[str, str]:
    action_title = {
        "archive": "Confirm Archive",
        "restore": "Confirm Restore",
        "pack": "Confirm Pack",
        "unpack": "Confirm Unpack",
        "toggle_pack": "Confirm Toggle Pack",
        "delete": "Confirm Delete",
        "review_meta": "Confirm Metadata Review",
        "rename_meta_ext": "Confirm Metadata Rename",
    }.get(action, "Confirm Action")

    lines: list[str] = []
    lines.append(f"[cyan]action[/]: {app._esc(action)}")
    lines.append(f"[cyan]items[/]: {len(paths)}")

    runnable_paths, skipped_paths = app._preflight_bulk_action(action, paths)
    skipped_by_path = {p: reason for p, reason in skipped_paths}
    lines.append(
        f"[cyan]preflight[/]: [green]{len(runnable_paths)} ready[/], [yellow]{len(skipped_paths)} skipped[/]"
    )
    if skipped_paths:
        lines.append(
            f"[yellow]skip reasons[/]: {app._esc(app._preflight_skip_summary(skipped_paths))}"
        )
    if action == "restore" and runnable_paths:
        conflict_count = 0
        for path in runnable_paths:
            try:
                target = archived_restore_target(base_dir, path)
                if target.exists():
                    conflict_count += 1
            except (OSError, ValueError):
                pass
        if conflict_count > 0:
            lines.append(
                f"[yellow]restore conflicts[/]: {conflict_count} target(s) already exist and will prompt during restore"
            )

    if action == "delete":
        lines.append("[bold red]warning[/]: this cannot be undone")
    elif action == "review_meta":
        lines.append("[cyan]effect[/]: open metadata file for manual fix guidance")
        lines.append("[cyan]kept[/]: no automatic metadata changes are performed")
        lines.append("")
        lines.append("[cyan]what to look for[/]:")
        lines.append("  - YAML must parse and root must be key:value mapping")
        lines.append("  - unknown top-level keys should be removed/renamed")
        lines.append("  - expected keys (optional): tags, description, wip, log")
    elif action == "rename_meta_ext":
        lines.append("[cyan]effect[/]: rename legacy .base.yml file to .base.yaml")

    lines.append("")
    lines.append("[cyan]target preview[/]:")
    max_preview = 8
    for path in paths[:max_preview]:
        reason = skipped_by_path.get(path)
        if action == "archive":
            lines.extend(
                _archive_preview_line(
                    app, path, base_dir, reason, is_under=is_under,
                )
            )
        elif action == "delete":
            lines.extend(
                _delete_preview_lines(
                    app, path, base_dir, reason, is_under=is_under,
                )
            )
        elif action == "restore":
            lines.extend(
                _restore_preview_lines(
                    app,
                    path,
                    base_dir,
                    reason,
                    is_under=is_under,
                    archived_restore_target=archived_restore_target,
                )
            )
        elif action in {"pack", "unpack", "toggle_pack"}:
            if is_packed_archive_path is None:
                lines.append(
                    _generic_preview_line(
                        app, path, base_dir, reason, is_under=is_under,
                    )
                )
            else:
                lines.extend(
                    _pack_preview_lines(
                        app,
                        path,
                        base_dir,
                        reason,
                        action=action,
                        is_under=is_under,
                        is_packed_path=is_packed_archive_path,
                    )
                )
        else:
            lines.append(
                _generic_preview_line(
                    app, path, base_dir, reason, is_under=is_under,
                )
            )
    if len(paths) > max_preview:
        lines.append(f"  [dim]... +{len(paths) - max_preview} more[/]")

    return action_title, "\n".join(lines)
