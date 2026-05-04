from __future__ import annotations

from pathlib import Path

from ..archive import io as archive_io
from ..archive import ops as archive_ops
from ..archive import service as archive_service
from ..cache.api import cache_delete_opened_ts, cache_move_opened_ts
from ..core import prompting
from ..core import utils as core_utils
from ..core.constants import (
    ARCHIVE_DIR_NAME,
    ARCHIVE_TZ,
    BASE_MARKER_FILE,
    ENV_BASE_DIR,
    PACKED_ARCHIVE_SUFFIX,
)
from ..core.models import RestoreTargetExistsError
from ..metadata.api import (
    append_base_log,
    ensure_base_marker,
    sync_tag_symlinks,
)
from ..workspace.rows import (
    archive_destination,
    archived_restore_target,
)
from . import workspace as commands_workspace


def _packed_cache_invalidate_path(path: Path) -> None:
    archive_io.invalidate_packed_cache_path(path)


def _validate_tar_archive_members(path):
    return archive_io.validate_tar_archive_members(path)


def _safe_extract_tar_to_dir(path: Path, target_dir: Path) -> None:
    archive_io.safe_extract_tar_to_dir(path, target_dir)


def is_packed_archive_path(path: Path) -> bool:
    return core_utils.is_packed_archive_path(path, PACKED_ARCHIVE_SUFFIX)


def normalize_restore_target(
    base_dir: Path, target: Path, allow_outside_base: bool = False
) -> Path:
    return core_utils.normalize_restore_target(
        base_dir, target, allow_outside_base=allow_outside_base
    )


def _prompt_readline(
    prompt: str,
    default: str | None = None,
    non_interactive_default: str | None = None,
) -> str | None:
    return prompting.prompt_readline(
        prompt,
        default=default,
        non_interactive_default=non_interactive_default,
    )


def _prompt_yes_no(question: str, default: bool) -> bool:
    return prompting.prompt_yes_no(question, default=default, read=_prompt_readline)


def archive_parent_for(src: Path, base_dir: Path) -> Path:
    return archive_ops.archive_parent_for(
        src,
        base_dir,
        archive_dir_name=ARCHIVE_DIR_NAME,
    )


def confirm() -> None:
    prompting.confirm(_prompt_readline)


def _ensure_safe_cwd(base_dir: Path, target: Path) -> None:
    archive_ops.ensure_safe_cwd(base_dir, target, is_under=core_utils.is_under)


def _archive_root(base_dir: Path) -> Path:
    return (base_dir / ARCHIVE_DIR_NAME).resolve()


def _policy_reason_outside_base(path: Path, base_dir: Path) -> str | None:
    if not core_utils.is_under(path, base_dir):
        return "outside base dir"
    return None


def _policy_reason_not_under_archive(path: Path, base_dir: Path) -> str | None:
    if not core_utils.is_under(path, _archive_root(base_dir)):
        return "not under _archive"
    return None


def _policy_reason_archived_entry(path: Path, base_dir: Path) -> str | None:
    if not path.is_dir() and not is_packed_archive_path(path):
        return "not archived entry"
    return _policy_reason_not_under_archive(path, base_dir)


def _policy_reason_archived_dir(path: Path, base_dir: Path) -> str | None:
    if not path.is_dir():
        return "not archived directory"
    return _policy_reason_not_under_archive(path, base_dir)


def _policy_reason_packed_archive(path: Path, base_dir: Path) -> str | None:
    if not is_packed_archive_path(path):
        return "not packed archive"
    return _policy_reason_not_under_archive(path, base_dir)


def _archive_require_dir(base_dir: Path, src: Path) -> None:
    reason = _policy_reason_archived_dir(src, base_dir)
    if reason:
        raise ValueError(f"not archived directory: {src}")


def _archive_require_packed(base_dir: Path, src: Path) -> None:
    reason = _policy_reason_packed_archive(src, base_dir)
    if reason:
        raise ValueError(f"not packed archived file: {src}")


def _archive_require_entry(base_dir: Path, src: Path) -> None:
    reason = _policy_reason_archived_entry(src, base_dir)
    if reason:
        raise ValueError(f"not archived entry: {src}")


def _archive_extract_single_root(
    src: Path, tmp_prefix: str, tmp_parent: Path
) -> tuple[Path, Path]:
    return archive_ops.archive_extract_single_root(
        src,
        tmp_prefix,
        tmp_parent,
        validate_tar_archive_members=_validate_tar_archive_members,
        safe_extract_tar_to_dir=_safe_extract_tar_to_dir,
    )


def _archive_sync_tags_if_needed(base_dir: Path, sync_tags: bool) -> None:
    if sync_tags:
        _ = sync_tag_symlinks(base_dir)


def archive_move_internal(base_dir: Path, src: Path, sync_tags: bool = True) -> Path:
    dst = archive_service.archive_move_internal(
        base_dir,
        src,
        policy_reason_outside_base=_policy_reason_outside_base,
        ensure_safe_cwd=_ensure_safe_cwd,
        archive_destination=archive_destination,
        sync_tags_if_needed=_archive_sync_tags_if_needed,
        sync_tags=sync_tags,
    )
    cache_move_opened_ts(base_dir, src, dst)
    return dst


def archive_pack_internal(base_dir: Path, src: Path) -> Path:
    dst = archive_service.archive_pack_internal(
        base_dir,
        src,
        archive_require_dir=_archive_require_dir,
        base_marker_file=BASE_MARKER_FILE,
        packed_archive_suffix=PACKED_ARCHIVE_SUFFIX,
        ensure_safe_cwd=_ensure_safe_cwd,
        invalidate_packed_cache_path=_packed_cache_invalidate_path,
    )
    cache_move_opened_ts(base_dir, src, dst)
    return dst


def archive_unpack_internal(base_dir: Path, src: Path) -> Path:
    dst = archive_service.archive_unpack_internal(
        base_dir,
        src,
        archive_require_packed=_archive_require_packed,
        packed_archive_dir_name=lambda path: core_utils.packed_archive_dir_name(
            path,
            PACKED_ARCHIVE_SUFFIX,
        ),
        archive_extract_single_root=_archive_extract_single_root,
        invalidate_packed_cache_path=_packed_cache_invalidate_path,
    )
    cache_move_opened_ts(base_dir, src, dst)
    return dst


def archive_restore_internal(
    base_dir: Path,
    src: Path,
    target_override: Path | None = None,
    sync_tags: bool = True,
    allow_outside_base: bool = False,
) -> Path:
    dst = archive_service.archive_restore_internal(
        base_dir,
        src,
        archive_require_entry=_archive_require_entry,
        archived_restore_target=archived_restore_target,
        normalize_restore_target=lambda b, t, allow: normalize_restore_target(
            b,
            t,
            allow_outside_base=allow,
        ),
        ensure_safe_cwd=_ensure_safe_cwd,
        remove_placeholder_target=_remove_placeholder_target,
        restore_target_exists_error_factory=lambda source, target: RestoreTargetExistsError(
            source,
            target,
        ),
        archive_extract_single_root=_archive_extract_single_root,
        invalidate_packed_cache_path=_packed_cache_invalidate_path,
        sync_tags_if_needed=_archive_sync_tags_if_needed,
        target_override=target_override,
        sync_tags=sync_tags,
        allow_outside_base=allow_outside_base,
    )
    cache_move_opened_ts(base_dir, src, dst)
    return dst


def delete_internal(base_dir: Path, target: Path, sync_tags: bool = True) -> None:
    archive_service.delete_internal(
        base_dir,
        target,
        ensure_safe_cwd=_ensure_safe_cwd,
        is_packed_archive_path=is_packed_archive_path,
        sync_tags_if_needed=_archive_sync_tags_if_needed,
        sync_tags=sync_tags,
    )
    cache_delete_opened_ts(base_dir, target)


def cmd_archive_mv(base_dir: Path, path: str = ".") -> int:
    return commands_workspace.cmd_archive_mv(
        base_dir,
        path,
        archive_destination=archive_destination,
        confirm=confirm,
        archive_move_internal=lambda bd, src: archive_move_internal(bd, src),
    )


def cmd_archive_ls(base_dir: Path, path: str = ".") -> int:
    return commands_workspace.cmd_archive_ls(
        base_dir,
        path,
        policy_reason_outside_base=_policy_reason_outside_base,
        archive_parent_for=archive_parent_for,
    )


def _remove_placeholder_target(target: Path) -> bool:
    return archive_ops.remove_placeholder_target(target)


def cmd_archive_restore_entry(base_dir: Path, archived_path: str) -> int:
    return commands_workspace.cmd_archive_restore_entry(
        base_dir,
        archived_path,
        archived_restore_target=archived_restore_target,
        confirm=confirm,
        archive_restore_internal=lambda bd, src: archive_restore_internal(bd, src),
    )


def cmd_archive_undo(base_dir: Path, path: str = ".") -> int:
    return commands_workspace.cmd_archive_undo(
        base_dir,
        path,
        policy_reason_outside_base=_policy_reason_outside_base,
        archive_parent_for=archive_parent_for,
        cmd_archive_restore_entry=cmd_archive_restore_entry,
    )


def cmd_rm(path: str = ".", force_outside_base: bool = False) -> int:
    return commands_workspace.cmd_rm(
        path,
        env_base_dir_key=ENV_BASE_DIR,
        policy_reason_outside_base=_policy_reason_outside_base,
        confirm=confirm,
        delete_internal=lambda bd, target: delete_internal(bd, target),
        force_outside_base=force_outside_base,
    )


def cmd_migrate(
    paths: list[str], archive_mode: bool = False, flat_mode: bool = False
) -> int:
    return commands_workspace.cmd_migrate(
        paths,
        archive_dir_name=ARCHIVE_DIR_NAME,
        split_archive_name=lambda name: core_utils.split_archive_name(
            name,
            parse_timestamp=lambda value: core_utils.parse_archive_timestamp(
                value,
                ARCHIVE_TZ,
            ),
        ),
        archive_iso_from_ts=lambda ts: core_utils.archive_iso_from_ts(ts, ARCHIVE_TZ),
        archive_now_iso=lambda: core_utils.archive_now_iso(ARCHIVE_TZ),
        is_under=core_utils.is_under,
        archive_destination=archive_destination,
        ensure_safe_cwd=_ensure_safe_cwd,
        ensure_base_marker=ensure_base_marker,
        append_base_log=append_base_log,
        sync_tag_symlinks=sync_tag_symlinks,
        confirm=confirm,
        archive_mode=archive_mode,
        flat_mode=flat_mode,
    )


def suggest_project_root(path: Path) -> Path:
    return commands_workspace.suggest_project_root(path)


def find_marker_root_upward(
    path: Path, marker_file: str = BASE_MARKER_FILE
) -> Path | None:
    return commands_workspace.find_marker_root_upward(path, marker_file)


def try_parse_archive_suffix_loose(suffix: str) -> int:
    return core_utils.parse_archive_timestamp(suffix, ARCHIVE_TZ)


def cmd_fix(path: str = ".") -> int:
    return commands_workspace.cmd_fix(
        path,
        env_base_dir_key=ENV_BASE_DIR,
        archive_dir_name=ARCHIVE_DIR_NAME,
        is_under=core_utils.is_under,
        suggest_project_root=suggest_project_root,
        base_marker_file=BASE_MARKER_FILE,
        prompt_yes_no=_prompt_yes_no,
        parse_archive_timestamp=try_parse_archive_suffix_loose,
        ensure_base_marker=ensure_base_marker,
        confirm=confirm,
    )
