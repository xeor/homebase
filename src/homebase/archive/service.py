from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Callable


def archive_move_internal(
    base_dir: Path,
    src: Path,
    *,
    policy_reason_outside_base: Callable[[Path, Path], str | None],
    ensure_safe_cwd: Callable[[Path, Path], None],
    archive_destination: Callable[[Path, Path], Path],
    sync_tags_if_needed: Callable[[Path, bool], None],
    sync_tags: bool,
) -> Path:
    if not src.is_dir():
        raise ValueError(f"not a directory: {src}")
    if policy_reason_outside_base(src, base_dir):
        raise ValueError(f"path not under base: {src}")

    ensure_safe_cwd(base_dir, src)
    dest = archive_destination(src, base_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src == Path.cwd().resolve():
        src.rename(dest)
        src.mkdir(parents=True, exist_ok=True)
        (src / ".archived-placeholder").write_text(str(dest) + "\n")
    else:
        src.rename(dest)
    sync_tags_if_needed(base_dir, sync_tags)
    return dest


def archive_pack_internal(
    base_dir: Path,
    src: Path,
    *,
    archive_require_dir: Callable[[Path, Path], None],
    base_marker_file: str,
    packed_archive_suffix: str,
    ensure_safe_cwd: Callable[[Path, Path], None],
    invalidate_packed_cache_path: Callable[[Path], None],
) -> Path:
    archive_require_dir(base_dir, src)
    if not (src / base_marker_file).is_file():
        raise ValueError(f"cannot pack: missing {base_marker_file}")

    target = src.with_name(f"{src.name}{packed_archive_suffix}")
    if target.exists():
        raise ValueError(f"target exists: {target.name}")

    tmp_fd, tmp_name = tempfile.mkstemp(prefix=f".{src.name}.", suffix=packed_archive_suffix, dir=str(src.parent))
    os.close(tmp_fd)
    tmp = Path(tmp_name)
    try:
        tar_bin = shutil.which("tar")
        if tar_bin is not None:
            proc = subprocess.run(
                [tar_bin, "-czf", str(tmp), "-C", str(src.parent), src.name],
                text=True,
                capture_output=True,
                check=False,
            )
            if proc.returncode != 0:
                err = (proc.stderr or "").strip() or (proc.stdout or "").strip() or "tar failed"
                raise ValueError(err)
        else:
            with tarfile.open(tmp, "w:gz") as tf:
                tf.add(src, arcname=src.name)
        ensure_safe_cwd(base_dir, src)
        tmp.replace(target)
        shutil.rmtree(src)
        invalidate_packed_cache_path(src)
        invalidate_packed_cache_path(target)
        return target
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def archive_unpack_internal(
    base_dir: Path,
    src: Path,
    *,
    archive_require_packed: Callable[[Path, Path], None],
    packed_archive_dir_name: Callable[[Path], str],
    archive_extract_single_root: Callable[[Path, str, Path], tuple[Path, Path]],
    invalidate_packed_cache_path: Callable[[Path], None],
) -> Path:
    archive_require_packed(base_dir, src)
    target = src.with_name(packed_archive_dir_name(src))
    if target.exists():
        raise ValueError(f"target exists: {target.name}")
    tmp_dir, root = archive_extract_single_root(src, ".pkg-unpack-", src.parent)
    try:
        root.rename(target)
        src.unlink(missing_ok=True)
        invalidate_packed_cache_path(src)
        invalidate_packed_cache_path(target)
        return target
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


def archive_restore_internal(
    base_dir: Path,
    src: Path,
    *,
    archive_require_entry: Callable[[Path, Path], None],
    archived_restore_target: Callable[[Path, Path], Path],
    normalize_restore_target: Callable[[Path, Path, bool], Path],
    ensure_safe_cwd: Callable[[Path, Path], None],
    remove_placeholder_target: Callable[[Path], bool],
    restore_target_exists_error_factory: Callable[[Path, Path], Exception],
    archive_extract_single_root: Callable[[Path, str, Path], tuple[Path, Path]],
    invalidate_packed_cache_path: Callable[[Path], None],
    sync_tags_if_needed: Callable[[Path, bool], None],
    target_override: Path | None,
    sync_tags: bool,
    allow_outside_base: bool,
) -> Path:
    archive_require_entry(base_dir, src)
    raw_target = target_override if target_override is not None else archived_restore_target(base_dir, src)
    target = normalize_restore_target(base_dir, raw_target, allow_outside_base)
    ensure_safe_cwd(base_dir, target)
    if target.exists() and not remove_placeholder_target(target):
        raise restore_target_exists_error_factory(src, target)

    target.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        src.rename(target)
        invalidate_packed_cache_path(src)
    else:
        tmp_dir, root = archive_extract_single_root(src, ".pkg-restore-", target.parent)
        try:
            root.rename(target)
            src.unlink(missing_ok=True)
            invalidate_packed_cache_path(src)
            invalidate_packed_cache_path(target)
        finally:
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir, ignore_errors=True)
    sync_tags_if_needed(base_dir, sync_tags)
    return target


def delete_internal(
    base_dir: Path,
    target: Path,
    *,
    ensure_safe_cwd: Callable[[Path, Path], None],
    is_packed_archive_path: Callable[[Path], bool],
    sync_tags_if_needed: Callable[[Path, bool], None],
    sync_tags: bool,
) -> None:
    if not target.exists():
        raise ValueError(f"not found: {target}")
    if target.is_dir():
        ensure_safe_cwd(base_dir, target)
        shutil.rmtree(target)
    elif is_packed_archive_path(target):
        target.unlink(missing_ok=True)
    else:
        raise ValueError(f"unsupported target type: {target}")
    sync_tags_if_needed(base_dir, sync_tags)
