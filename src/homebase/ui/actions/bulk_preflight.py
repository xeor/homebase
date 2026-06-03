from __future__ import annotations

from pathlib import Path
from typing import Callable


def _packed_target_exists_for_dir(path: Path) -> bool:
    return path.with_name(f"{path.name}.tgz").is_file()


def _reason_archive(
    path: Path,
    *,
    base_dir: Path,
    policy_reason_outside_base: Callable[[Path, Path], str | None],
    policy_reason_not_under_archive: Callable[[Path, Path], str | None],
) -> str:
    if not path.exists():
        return "missing path"
    if not path.is_dir():
        return "not a directory"
    reason = policy_reason_outside_base(path, base_dir) or ""
    if not reason and policy_reason_not_under_archive(path, base_dir) is None:
        return "already in _archive"
    return reason


def _reason_restore(
    path: Path,
    *,
    base_dir: Path,
    policy_reason_archived_entry: Callable[[Path, Path], str | None],
) -> str:
    if not path.exists():
        return "missing path"
    return policy_reason_archived_entry(path, base_dir) or ""


def _reason_pack(
    path: Path,
    *,
    base_dir: Path,
    base_marker_file: str,
    is_packed_archive_path: Callable[[Path], bool],
    policy_reason_archived_dir: Callable[[Path, Path], str | None],
) -> str:
    if is_packed_archive_path(path):
        return "already packed"
    if not path.exists():
        return "missing path"
    reason = policy_reason_archived_dir(path, base_dir) or ""
    if reason:
        return reason
    if not (path / base_marker_file).is_file():
        return f"missing {base_marker_file}"
    if _packed_target_exists_for_dir(path):
        return "packed target exists"
    return ""


def _reason_unpack(
    path: Path,
    *,
    base_dir: Path,
    packed_archive_dir_name: Callable[[Path], str],
    policy_reason_packed_archive: Callable[[Path, Path], str | None],
) -> str:
    if not path.exists():
        return "missing path"
    reason = policy_reason_packed_archive(path, base_dir) or ""
    if reason:
        return reason
    if path.with_name(packed_archive_dir_name(path)).exists():
        return "unpack target exists"
    return ""


def _reason_toggle_pack(
    path: Path,
    *,
    base_dir: Path,
    base_marker_file: str,
    is_packed_archive_path: Callable[[Path], bool],
    packed_archive_dir_name: Callable[[Path], str],
    policy_reason_archived_dir: Callable[[Path, Path], str | None],
    policy_reason_packed_archive: Callable[[Path, Path], str | None],
) -> str:
    if is_packed_archive_path(path):
        return _reason_unpack(
            path,
            base_dir=base_dir,
            packed_archive_dir_name=packed_archive_dir_name,
            policy_reason_packed_archive=policy_reason_packed_archive,
        )
    return _reason_pack(
        path,
        base_dir=base_dir,
        base_marker_file=base_marker_file,
        is_packed_archive_path=is_packed_archive_path,
        policy_reason_archived_dir=policy_reason_archived_dir,
    )


def _reason_delete(
    path: Path,
    *,
    base_dir: Path,
    policy_reason_outside_base: Callable[[Path, Path], str | None],
) -> str:
    if not path.exists():
        return "missing path"
    return policy_reason_outside_base(path, base_dir) or ""


def _reason_deworktree(path: Path) -> str:
    if not path.exists():
        return "missing path"
    if not path.is_dir():
        return "not a directory"
    return ""


def _reason_review_meta(
    path: Path,
    *,
    base_marker_file: str,
    legacy_base_marker_file: str,
    is_packed_archive_path: Callable[[Path], bool],
) -> str:
    if is_packed_archive_path(path):
        return "not supported for packed archive"
    if not path.exists():
        return "missing path"
    if not (
        (path / base_marker_file).exists()
        or (path / legacy_base_marker_file).exists()
    ):
        return "metadata file missing"
    return ""


def _reason_rename_meta_ext(
    path: Path,
    *,
    base_marker_file: str,
    legacy_base_marker_file: str,
    is_packed_archive_path: Callable[[Path], bool],
) -> str:
    if is_packed_archive_path(path):
        return "not supported for packed archive"
    if not path.exists():
        return "missing path"
    if not (path / legacy_base_marker_file).is_file():
        return f"no {legacy_base_marker_file}"
    if (path / base_marker_file).exists():
        return f"{base_marker_file} already exists"
    return ""


def _resolve_reason(
    action: str,
    path: Path,
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
) -> str:
    if action == "archive":
        return _reason_archive(
            path,
            base_dir=base_dir,
            policy_reason_outside_base=policy_reason_outside_base,
            policy_reason_not_under_archive=policy_reason_not_under_archive,
        )
    if action == "restore":
        return _reason_restore(
            path,
            base_dir=base_dir,
            policy_reason_archived_entry=policy_reason_archived_entry,
        )
    if action == "pack":
        return _reason_pack(
            path,
            base_dir=base_dir,
            base_marker_file=base_marker_file,
            is_packed_archive_path=is_packed_archive_path,
            policy_reason_archived_dir=policy_reason_archived_dir,
        )
    if action == "unpack":
        return _reason_unpack(
            path,
            base_dir=base_dir,
            packed_archive_dir_name=packed_archive_dir_name,
            policy_reason_packed_archive=policy_reason_packed_archive,
        )
    if action == "toggle_pack":
        return _reason_toggle_pack(
            path,
            base_dir=base_dir,
            base_marker_file=base_marker_file,
            is_packed_archive_path=is_packed_archive_path,
            packed_archive_dir_name=packed_archive_dir_name,
            policy_reason_archived_dir=policy_reason_archived_dir,
            policy_reason_packed_archive=policy_reason_packed_archive,
        )
    if action == "delete":
        return _reason_delete(
            path,
            base_dir=base_dir,
            policy_reason_outside_base=policy_reason_outside_base,
        )
    if action == "deworktree":
        return _reason_deworktree(path)
    if action == "review_meta":
        return _reason_review_meta(
            path,
            base_marker_file=base_marker_file,
            legacy_base_marker_file=legacy_base_marker_file,
            is_packed_archive_path=is_packed_archive_path,
        )
    if action == "rename_meta_ext":
        return _reason_rename_meta_ext(
            path,
            base_marker_file=base_marker_file,
            legacy_base_marker_file=legacy_base_marker_file,
            is_packed_archive_path=is_packed_archive_path,
        )
    return ""


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
        reason = _resolve_reason(
            action,
            path,
            base_dir=base_dir,
            base_marker_file=base_marker_file,
            legacy_base_marker_file=legacy_base_marker_file,
            is_packed_archive_path=is_packed_archive_path,
            packed_archive_dir_name=packed_archive_dir_name,
            policy_reason_outside_base=policy_reason_outside_base,
            policy_reason_not_under_archive=policy_reason_not_under_archive,
            policy_reason_archived_entry=policy_reason_archived_entry,
            policy_reason_archived_dir=policy_reason_archived_dir,
            policy_reason_packed_archive=policy_reason_packed_archive,
        )
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
