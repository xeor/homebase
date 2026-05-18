from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..archive import io as archive_io
from ..archive import ops as archive_ops
from ..archive import service as archive_service
from ..cache.api import cache_delete_opened_ts, cache_move_opened_ts
from ..core import prompting
from ..core import utils as core_utils
from ..core.constants import (
    ARCHIVE_DIR_NAME,
    ARCHIVE_TZ,
    ARCHIVE_YEAR_DIR_RE,
    BASE_MARKER_FILE,
    ENV_BASE_DIR,
    PACKED_ARCHIVE_SUFFIX,
)
from ..core.models import RestoreTargetExistsError
from ..hooks.runtime import dispatch_post_cli, dispatch_pre_cli
from ..hooks.snapshot import snapshot_target_from_path
from ..metadata.api import (
    append_base_log,
    cleanup_tag_symlinks_pointing_at,
    ensure_base_marker,
    sync_tag_symlinks,
)
from ..tmux.flow import open_shell_in_dir
from ..workspace.rows import (
    archive_destination,
    archived_restore_target,
)
from . import workspace as commands_workspace


def _exec_shell_at_parent_if_cwd_under(
    target: Path,
    base_dir: Path,
    *,
    original_cwd: Path | None = None,
) -> None:
    """When the user just deleted or archived ``target`` and the
    shell-process cwd at the start of the command was at or under
    that target, the shell is now pointing at a phantom directory.
    Drop the user into a fresh shell at the parent (falling back to
    ``base_dir`` if the parent is gone too).

    The caller MUST pass ``original_cwd`` (the cwd captured BEFORE any
    inner ``os.chdir`` from archive/delete) — by the time we reach
    this helper, ``archive_service`` has already chdir'd to base, so
    ``Path.cwd()`` here is no longer a useful signal.

    No-op outside a TTY — ``open_shell_in_dir`` already guards itself.
    """
    if original_cwd is None:
        try:
            original_cwd = Path.cwd().resolve()
        except OSError:
            return
    if original_cwd != target and target not in original_cwd.parents:
        return
    parent = target.parent
    if not parent.is_dir():
        parent = base_dir
    open_shell_in_dir(parent)


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


def _packed_archive_name(src: Path) -> str:
    stem, ts = core_utils.split_archive_name(
        src.name,
        parse_timestamp=lambda value: core_utils.parse_archive_timestamp(
            value,
            ARCHIVE_TZ,
        ),
    )
    if ts > 0:
        date_prefix = core_utils.archive_iso_from_ts(ts, ARCHIVE_TZ)[:10]
    else:
        date_prefix = core_utils.archive_now_iso(ARCHIVE_TZ)[:10]
    return f"{date_prefix}_{stem}{PACKED_ARCHIVE_SUFFIX}"


def _archive_entry_ts_iso(path: Path) -> str:
    _stem, ts = core_utils.split_archive_entry_name(
        path,
        packed_archive_suffix=PACKED_ARCHIVE_SUFFIX,
        parse_timestamp=lambda value: core_utils.parse_archive_timestamp(
            value,
            ARCHIVE_TZ,
        ),
    )
    if ts <= 0:
        return ""
    return core_utils.archive_iso_from_ts(ts, ARCHIVE_TZ)


def archive_move_internal(
    base_dir: Path,
    src: Path,
    sync_tags: bool = True,
    *,
    archive_destination_override: Callable[[Path, Path], Path] | None = None,
) -> Path:
    # ``sync_tags=False`` to the inner service so it skips the full
    # ``sync_tag_symlinks`` rebuild (walks every project under
    # ``base/`` — 10+ seconds on a real workspace). We follow up with
    # a targeted cleanup that only touches symlinks pointing at the
    # path we just moved.
    src_resolved = src.resolve() if src.exists() else src
    dest_fn = archive_destination_override or archive_destination
    dst = archive_service.archive_move_internal(
        base_dir,
        src,
        policy_reason_outside_base=_policy_reason_outside_base,
        ensure_safe_cwd=_ensure_safe_cwd,
        archive_destination=dest_fn,
        sync_tags_if_needed=_archive_sync_tags_if_needed,
        sync_tags=False,
    )
    if sync_tags:
        cleanup_tag_symlinks_pointing_at(base_dir, src_resolved)
    cache_move_opened_ts(base_dir, src, dst)
    append_base_log(
        dst,
        "archived",
        {
            "source_path": str(src),
            "archive_path": str(dst),
            "archive_entry": str(dst.name),
            "archive_entry_ts": _archive_entry_ts_iso(dst),
        },
    )
    return dst


def archive_pack_internal(base_dir: Path, src: Path) -> Path:
    dst = archive_service.archive_pack_internal(
        base_dir,
        src,
        archive_require_dir=_archive_require_dir,
        base_marker_file=BASE_MARKER_FILE,
        packed_archive_name=_packed_archive_name,
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
    archive_entry_ts = _archive_entry_ts_iso(src)
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
    append_base_log(
        dst,
        "restored",
        {
            "archive_path": str(src),
            "restored_path": str(dst),
            "archive_entry": str(src.name),
            "archive_entry_ts": archive_entry_ts,
        },
    )
    return dst


def delete_internal(base_dir: Path, target: Path, sync_tags: bool = True) -> None:
    # Snapshot the resolved target before deletion so we know what
    # the now-stale _tags/ symlinks would have been pointing at. The
    # inner service does ``sync_tags=False`` (no full rebuild) and we
    # finish with a targeted cleanup of just the affected symlinks.
    target_resolved = target.resolve() if target.exists() else target
    archive_service.delete_internal(
        base_dir,
        target,
        ensure_safe_cwd=_ensure_safe_cwd,
        is_packed_archive_path=is_packed_archive_path,
        sync_tags_if_needed=_archive_sync_tags_if_needed,
        sync_tags=False,
    )
    if sync_tags:
        cleanup_tag_symlinks_pointing_at(base_dir, target_resolved)
    cache_delete_opened_ts(base_dir, target)


def _archive_dest_with_forced_ts(forced_ts: int) -> Callable[[Path, Path], Path]:
    """Build an ``archive_destination`` callable that ignores any date
    parsed from the source name and uses ``forced_ts`` instead."""
    forced_iso = core_utils.archive_iso_from_ts(forced_ts, ARCHIVE_TZ)

    def _split_no_ts(name: str) -> tuple[str, int]:
        stem, _ = core_utils.split_archive_name(
            name,
            parse_timestamp=lambda v: core_utils.parse_archive_timestamp(v, ARCHIVE_TZ),
        )
        return stem, 0

    def _dest(src: Path, base_dir: Path) -> Path:
        return archive_ops.archive_destination(
            src,
            base_dir,
            archive_dir_name=ARCHIVE_DIR_NAME,
            split_archive_name=_split_no_ts,
            archive_iso_from_ts=lambda ts: core_utils.archive_iso_from_ts(ts, ARCHIVE_TZ),
            archive_now_iso=lambda: forced_iso,
        )

    return _dest


def _resolve_autodate_ts(src: Path, *, yes: bool) -> int | None:
    """Pick a timestamp for ``src`` using the shared detector. Falls
    back to prompting (default today) when nothing can be inferred.
    With --yes / no TTY, the today fallback is used silently."""
    from ..archive import date_detect

    detection = date_detect.detect_folder_date(
        src,
        parse_timestamp=lambda v: core_utils.parse_archive_timestamp(v, ARCHIVE_TZ),
        archive_tz=ARCHIVE_TZ,
    )
    if detection is not None:
        print(f"autodate: {detection.source}")
        return detection.ts
    import sys

    today_dt = datetime.now(ARCHIVE_TZ)
    today_iso = today_dt.strftime("%Y-%m-%d")
    today_ts = int(
        today_dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    )
    if yes or not sys.stdin.isatty():
        print(f"autodate: no date found, using today ({today_iso})")
        return today_ts
    for _ in range(3):
        raw = _prompt_readline(
            f"  date for '{src.name}' [YYYY-MM-DD, default {today_iso}]: ",
            default="",
            non_interactive_default="",
        )
        if raw is None:
            print("aborted: no valid date", file=sys.stderr)
            return None
        text = raw.strip()
        if not text:
            print(f"autodate: using today ({today_iso})")
            return today_ts
        parsed = date_detect.parse_user_date(text, ARCHIVE_TZ)
        if parsed is not None:
            print(f"autodate: user input {text}")
            return parsed
        print("  invalid date format, expected YYYY-MM-DD", file=sys.stderr)
    print("  giving up: no valid date", file=sys.stderr)
    return None


def cmd_archive_mv(
    base_dir: Path,
    paths: list[str] | str | None = None,
    *,
    autodate: bool = False,
    yes: bool = False,
) -> int:
    # Back-compat for old single-path callers (e.g. ``b a``).
    if paths is None:
        targets: list[str] = ["."]
    elif isinstance(paths, str):
        targets = [paths]
    else:
        targets = list(paths) if paths else ["."]
    try:
        original_cwd = Path.cwd().resolve()
    except OSError:
        original_cwd = base_dir
    worst = 0
    for idx, raw in enumerate(targets):
        if idx > 0:
            print("")
        if len(targets) > 1:
            print(f"== {raw} ==")
        src = Path(raw).resolve()
        if autodate:
            forced_ts = _resolve_autodate_ts(src, yes=yes)
            if forced_ts is None:
                worst = max(worst, 1)
                continue
            dest_fn = _archive_dest_with_forced_ts(forced_ts)
            move_fn = lambda bd, s, _dst=dest_fn: archive_move_internal(  # noqa: E731
                bd, s, archive_destination_override=_dst,
            )
        else:
            dest_fn = archive_destination
            move_fn = lambda bd, s: archive_move_internal(bd, s)  # noqa: E731
        rc = commands_workspace.cmd_archive_mv_one(
            base_dir,
            raw,
            archive_destination=dest_fn,
            confirm=confirm,
            archive_move_internal=move_fn,
            skip_confirm=yes,
        )
        if rc == 0:
            _exec_shell_at_parent_if_cwd_under(
                src, base_dir, original_cwd=original_cwd,
            )
        else:
            worst = max(worst, rc)
    return worst


def cmd_archive_ls(base_dir: Path, path: str = ".") -> int:
    return commands_workspace.cmd_archive_ls(
        base_dir,
        path,
        policy_reason_outside_base=_policy_reason_outside_base,
        archive_root=_archive_root,
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
        archive_root=_archive_root,
        cmd_archive_restore_entry=cmd_archive_restore_entry,
    )


def cmd_rm(
    path: str = ".",
    force_outside_base: bool = False,
    *,
    force: bool = False,
    hook_specs: dict[tuple[str, str], list[object]] | None = None,
) -> int:
    target = Path(path).resolve()
    base_dir = Path(os.environ.get(ENV_BASE_DIR, ".")).resolve()
    # Snapshot cwd BEFORE delete_internal -> archive_service does an
    # ``os.chdir(base_dir)`` internally to escape the target. Without
    # this snapshot the safety check below sees cwd == base_dir and
    # never spawns the recovery shell, so the user's parent shell is
    # left sitting in a deleted directory.
    try:
        original_cwd = Path.cwd().resolve()
    except OSError:
        original_cwd = base_dir
    delete_target = None
    removed_snapshot: dict[Path, dict[str, object]] = {}
    if target.exists() and target.is_dir():
        try:
            delete_target = snapshot_target_from_path(
                target,
                archived=core_utils.is_under(target, _archive_root(base_dir)),
            )
            removed_snapshot[target] = {
                "name": delete_target.name,
                "archived": delete_target.archived,
                "tags": list(delete_target.tags),
                "properties": list(delete_target.properties),
                "description": delete_target.description,
                "wip": delete_target.wip,
                "suffix": delete_target.suffix,
                "packed": delete_target.packed,
                "base_meta": dict(delete_target.base_meta),
            }
        except OSError:
            delete_target = None
    if hook_specs and delete_target is not None:
        pre_outcome = dispatch_pre_cli(
            base_dir=base_dir,
            hook_specs=hook_specs,
            event="delete",
            targets=[delete_target],
            change={
                "removed_paths": [delete_target.path],
                "removed_snapshots": removed_snapshot,
            },
            view="archive" if delete_target.archived else "active",
        )
        if pre_outcome.cancelled:
            print(f"delete cancelled by hook: {pre_outcome.reason}", file=os.sys.stderr)
            return 1
    rc = commands_workspace.cmd_rm(
        path,
        env_base_dir_key=ENV_BASE_DIR,
        policy_reason_outside_base=_policy_reason_outside_base,
        prompt_yes_no=_prompt_yes_no,
        delete_internal=lambda bd, target: delete_internal(bd, target),
        force_outside_base=force_outside_base,
        force=force,
    )
    if rc == 0:
        if hook_specs and delete_target is not None:
            dispatch_post_cli(
                base_dir=base_dir,
                hook_specs=hook_specs,
                event="delete",
                targets=[delete_target],
                change={
                    "removed_paths": [delete_target.path],
                    "removed_snapshots": removed_snapshot,
                },
                view="archive" if delete_target.archived else "active",
            )
        _exec_shell_at_parent_if_cwd_under(
            target, base_dir, original_cwd=original_cwd,
        )
    return rc




def suggest_project_root(path: Path) -> Path:
    return commands_workspace.suggest_project_root(path)


def find_marker_root_upward(
    path: Path, marker_file: str = BASE_MARKER_FILE
) -> Path | None:
    return commands_workspace.find_marker_root_upward(path, marker_file)


def try_parse_archive_suffix_loose(suffix: str) -> int:
    return core_utils.parse_archive_timestamp(suffix, ARCHIVE_TZ)


def cmd_fix(
    paths: list[str] | None = None,
    *,
    include: set[str] | None = None,
    yes: bool = False,
    all_targets: bool = False,
) -> int:
    import sys

    from ..archive import date_detect

    # ``b fix`` prompts should let Ctrl-C abort the whole sweep, not
    # just decline the current item. Use the strict readline variant
    # that re-raises KeyboardInterrupt instead of swallowing it.
    def _read_line_strict(question: str) -> str | None:
        return prompting.prompt_readline(
            question,
            default="",
            non_interactive_default="",
            abort_on_interrupt=True,
        )

    def _prompt_yes_no_strict(question: str, default: bool) -> bool:
        return prompting.prompt_yes_no(
            question, default=default, read=_read_line_strict,
        )

    selected = (
        set(include)
        if include is not None
        else set(commands_workspace.FIX_KINDS)
    )
    try:
        return commands_workspace.cmd_fix(
            list(paths) if paths is not None else ["."],
            include=selected,
            yes=yes,
            all_targets=all_targets,
            env_base_dir_key=ENV_BASE_DIR,
            archive_dir_name=ARCHIVE_DIR_NAME,
            archive_year_re=ARCHIVE_YEAR_DIR_RE,
            archive_tz=ARCHIVE_TZ,
            is_under=core_utils.is_under,
            base_marker_file=BASE_MARKER_FILE,
            prompt_yes_no=_prompt_yes_no_strict,
            parse_archive_timestamp=try_parse_archive_suffix_loose,
            archive_iso_from_ts=core_utils.archive_iso_from_ts,
            detect_folder_date=date_detect.detect_folder_date,
            parse_user_date=date_detect.parse_user_date,
            strip_date_prefix=date_detect.strip_date_prefix,
            ensure_base_marker=ensure_base_marker,
            read_line=_read_line_strict,
        )
    except KeyboardInterrupt:
        print()
        print("aborted by user (^C)", file=sys.stderr)
        return 130
