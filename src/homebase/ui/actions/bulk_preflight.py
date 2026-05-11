from __future__ import annotations

from pathlib import Path
from typing import Callable


def _packed_target_exists_for_dir(path: Path) -> bool:
    pattern = f"*_{path.name}.tgz"
    for hit in path.parent.glob(pattern):
        if hit.is_file():
            return True
    return False


def preflight_bulk_action(
    action: str,
    paths: list[Path],
    *,
    base_dir: Path,
    base_marker_file: str,
    legacy_base_marker_file: str,
    is_packed_archive_path: Callable[[Path], bool],
    packed_archive_dir_name: Callable[[Path], str],
    policy_reason_outside_base: Callable[[Path, Path], str | None],
    policy_reason_not_under_archive: Callable[[Path, Path], str | None],
    policy_reason_archived_entry: Callable[[Path, Path], str | None],
    policy_reason_archived_dir: Callable[[Path, Path], str | None],
    policy_reason_packed_archive: Callable[[Path, Path], str | None],
) -> tuple[list[Path], list[tuple[Path, str]]]:
    runnable: list[Path] = []
    skipped: list[tuple[Path, str]] = []

    for path in paths:
        reason = ""
        exists = path.exists()

        if action == "archive":
            if not exists:
                reason = "missing path"
            elif not path.is_dir():
                reason = "not a directory"
            else:
                reason = policy_reason_outside_base(path, base_dir) or ""
                if not reason and policy_reason_not_under_archive(path, base_dir) is None:
                    reason = "already in _archive"
        elif action == "restore":
            if not exists:
                reason = "missing path"
            else:
                reason = policy_reason_archived_entry(path, base_dir) or ""
        elif action == "pack":
            if is_packed_archive_path(path):
                reason = "already packed"
            elif not exists:
                reason = "missing path"
            else:
                reason = policy_reason_archived_dir(path, base_dir) or ""
            if not reason and not (path / base_marker_file).is_file():
                reason = f"missing {base_marker_file}"
            elif not reason and _packed_target_exists_for_dir(path):
                reason = "packed target exists"
        elif action == "unpack":
            if not exists:
                reason = "missing path"
            else:
                reason = policy_reason_packed_archive(path, base_dir) or ""
            if not reason and path.with_name(packed_archive_dir_name(path)).exists():
                reason = "unpack target exists"
        elif action == "toggle_pack":
            if is_packed_archive_path(path):
                if not exists:
                    reason = "missing path"
                else:
                    reason = policy_reason_packed_archive(path, base_dir) or ""
                if not reason and path.with_name(packed_archive_dir_name(path)).exists():
                    reason = "unpack target exists"
            else:
                if not exists:
                    reason = "missing path"
                else:
                    reason = policy_reason_archived_dir(path, base_dir) or ""
                if not reason and not (path / base_marker_file).is_file():
                    reason = f"missing {base_marker_file}"
                elif not reason and _packed_target_exists_for_dir(path):
                    reason = "packed target exists"
        elif action == "delete":
            if not exists:
                reason = "missing path"
            else:
                reason = policy_reason_outside_base(path, base_dir) or ""
        elif action == "review_meta":
            if is_packed_archive_path(path):
                reason = "not supported for packed archive"
            elif not exists:
                reason = "missing path"
            elif not (
                (path / base_marker_file).exists()
                or (path / legacy_base_marker_file).exists()
            ):
                reason = "metadata file missing"
        elif action == "rename_meta_ext":
            if is_packed_archive_path(path):
                reason = "not supported for packed archive"
            elif not exists:
                reason = "missing path"
            elif not (path / legacy_base_marker_file).is_file():
                reason = f"no {legacy_base_marker_file}"
            elif (path / base_marker_file).exists():
                reason = f"{base_marker_file} already exists"

        if reason:
            skipped.append((path, reason))
        else:
            runnable.append(path)

    return runnable, skipped


def preflight_skip_summary(skipped: list[tuple[Path, str]]) -> str:
    if not skipped:
        return ""
    counts: dict[str, int] = {}
    for _path, reason in skipped:
        counts[reason] = counts.get(reason, 0) + 1
    parts = [f"{reason} x{counts[reason]}" for reason in sorted(counts.keys())]
    return ", ".join(parts)
