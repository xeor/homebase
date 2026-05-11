from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def build_bulk_confirm_payload(
    app: Any,
    action: str,
    paths: list[Path],
    *,
    base_dir: Path,
    archived_restore_target: Callable[[Path, Path], Path],
    is_under: Callable[[Path, Path], bool],
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
                if archived_restore_target(base_dir, path).exists():
                    conflict_count += 1
            except (OSError, ValueError):
                pass
        if conflict_count > 0:
            lines.append(
                f"[yellow]restore conflicts[/]: {conflict_count} target(s) already exist and will prompt during restore"
            )

    if action == "archive":
        lines.append("[cyan]effect[/]: move selected project folders into [bold]_archive[/]")
    elif action == "restore":
        lines.append("[cyan]effect[/]: move selected archive folders back to restore targets")
    elif action == "pack":
        lines.append("[cyan]effect[/]: compress selected archive folders to .tgz")
    elif action == "unpack":
        lines.append("[cyan]effect[/]: expand selected .tgz files back to folders")
    elif action == "toggle_pack":
        lines.append("[cyan]effect[/]: pack folders and unpack .tgz entries in one pass")
    elif action == "delete":
        lines.append("[cyan]effect[/]: permanently remove selected folders from disk")
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
        lines.append("[cyan]kept[/]: metadata content and project files are unchanged")

    lines.append("")
    lines.append("[cyan]target preview[/]:")
    max_preview = 8
    for path in paths[:max_preview]:
        hit = app._find_row(path)
        reason = skipped_by_path.get(path)
        if hit is None:
            rel = app._esc(str(path))
            if reason:
                lines.append(f"  - {rel} [yellow](skip: {app._esc(reason)})[/]")
            else:
                lines.append(f"  - {rel} [green](ready)[/]")
            continue
        rows, idx = hit
        row = rows[idx]
        rel = app._esc(str(path.relative_to(base_dir)) if is_under(path, base_dir) else str(path))
        if action == "restore" and row.restore_target is not None:
            target = app._esc(str(row.restore_target))
            if reason:
                lines.append(
                    f"  - {rel} [dim]-> {target}[/] [yellow](skip: {app._esc(reason)})[/]"
                )
            else:
                lines.append(f"  - {rel} [dim]-> {target}[/] [green](ready)[/]")
        else:
            if reason:
                lines.append(f"  - {rel} [yellow](skip: {app._esc(reason)})[/]")
            else:
                lines.append(f"  - {rel} [green](ready)[/]")
    if len(paths) > max_preview:
        lines.append(f"  [dim]... +{len(paths) - max_preview} more[/]")

    return action_title, "\n".join(lines)
