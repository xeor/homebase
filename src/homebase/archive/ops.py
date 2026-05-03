from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Callable


def resolve_archive_prefix(src: Path, base_dir: Path) -> str:
    cur = src
    while True:
        marker = cur / ".archive_prefix"
        if marker.is_file():
            return marker.read_text().strip()
        parent = cur.parent
        if parent == base_dir or parent == cur:
            break
        cur = parent
    return ""


def archive_destination(
    src: Path,
    base_dir: Path,
    *,
    archive_dir_name: str,
    split_archive_name: Callable[[str], tuple[str, int]],
    archive_iso_from_ts: Callable[[int], str],
    archive_now_iso: Callable[[], str],
) -> Path:
    archive_root = base_dir / archive_dir_name
    rel = src.relative_to(base_dir)
    prefix = resolve_archive_prefix(src, base_dir)
    stem, parsed_ts = split_archive_name(src.name)
    ts = archive_iso_from_ts(parsed_ts) if parsed_ts > 0 else archive_now_iso()
    if prefix and rel.parent != Path("."):
        return archive_root / rel.parent / prefix / f"{stem}.{ts}"
    if prefix:
        return archive_root / prefix / f"{stem}.{ts}"
    if rel.parent != Path("."):
        return archive_root / rel.parent / f"{stem}.{ts}"
    return archive_root / f"{stem}.{ts}"


def archive_parent_for(src: Path, base_dir: Path, *, archive_dir_name: str) -> Path:
    rel = src.relative_to(base_dir)
    prefix = resolve_archive_prefix(src, base_dir)
    root = base_dir / archive_dir_name
    if prefix and rel.parent != Path("."):
        return root / rel.parent / prefix
    if prefix:
        return root / prefix
    if rel.parent != Path("."):
        return root / rel.parent
    return root


def ensure_safe_cwd(
    base_dir: Path,
    target: Path,
    *,
    is_under: Callable[[Path, Path], bool],
) -> None:
    cwd = Path.cwd().resolve()
    if cwd == target or is_under(cwd, target):
        os.chdir(base_dir)


def archive_extract_single_root(
    src: Path,
    tmp_prefix: str,
    tmp_parent: Path,
    *,
    validate_tar_archive_members: Callable[[Path], list[tarfile.TarInfo]],
    safe_extract_tar_to_dir: Callable[[Path, Path], None],
) -> tuple[Path, Path]:
    tmp_dir = Path(tempfile.mkdtemp(prefix=tmp_prefix, dir=str(tmp_parent)))
    try:
        _ = validate_tar_archive_members(src)
        tar_bin = shutil.which("tar")
        if tar_bin is not None:
            proc = subprocess.run(
                [tar_bin, "-xzf", str(src), "-C", str(tmp_dir)],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            if proc.returncode != 0:
                err = (proc.stderr or "").strip() or (proc.stdout or "").strip() or "tar failed"
                raise ValueError(err)
        else:
            safe_extract_tar_to_dir(src, tmp_dir)

        roots = [path for path in tmp_dir.iterdir() if path.exists()]
        if len(roots) != 1:
            raise ValueError(f"packed archive must contain exactly one top-level root (got {len(roots)})")
        root = roots[0]
        if not root.is_dir():
            raise ValueError("packed archive root must be a directory")
        return tmp_dir, root
    except (OSError, ValueError, tarfile.TarError):
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def remove_placeholder_target(target: Path) -> bool:
    if not target.exists() or not target.is_dir():
        return False
    placeholder = target / ".archived-placeholder"
    if not placeholder.is_file():
        return False
    extra = [entry for entry in target.iterdir() if entry.name != ".archived-placeholder"]
    if extra:
        return False
    placeholder.unlink(missing_ok=True)
    target.rmdir()
    return True
