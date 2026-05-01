from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from ..core import utils as core_utils
from ..core.constants import (
    DATE_PREFIX_RE,
    PACKED_ARCHIVE_SUFFIX,
    SIZE_REFRESH_EVERY_N,
    SUFFIXES,
)
from ..core.models import ProjectRow
from ..metadata.api import (
    base_meta_health,
    detect_properties,
    ensure_base_marker,
    load_base_meta,
    normalize_property_keys,
    save_base_tags,
)


def discover_copier_templates(base_dir: Path) -> list[str]:
    root = base_dir / ".copier"
    if not root.is_dir():
        return []
    out: list[str] = []
    for p in sorted(root.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_dir() or p.name.startswith("."):
            continue
        out.append(p.name)
    return out


def resolve_new_project_name(
    base_name: str, add_date_prefix: bool, add_tmp_suffix: bool
) -> str:
    trimmed = base_name.strip()
    if not trimmed:
        raise ValueError("folder name is empty")
    if trimmed in {".", ".."}:
        raise ValueError("folder name is invalid")
    if "/" in trimmed or "\\" in trimmed:
        raise ValueError("folder name must not contain path separators")

    core = DATE_PREFIX_RE.sub("", trimmed)
    if core.endswith(".tmp"):
        core = core[:-4]

    final_name = core
    if add_tmp_suffix:
        final_name = f"{final_name}.tmp"
    if add_date_prefix:
        final_name = f"{datetime.now().strftime('%Y-%d-%m_')}{final_name}"
    return final_name


def scaffold_template_directory(template_dir: Path, target_dir: Path) -> None:
    entries = list(template_dir.iterdir())
    if not entries:
        return
    for entry in entries:
        dest = target_dir / entry.name
        if entry.is_dir():
            shutil.copytree(entry, dest)
        else:
            shutil.copy2(entry, dest)


def run_post_commands(target_dir: Path, commands: list[str]) -> None:
    if not commands:
        return
    print(f"running post commands in {target_dir}:")
    for cmd in commands:
        print(f"$ {cmd}")
        try:
            result = subprocess.run(
                cmd, cwd=target_dir, shell=True, check=False, text=True
            )
        except subprocess.CalledProcessError as exc:
            details = exc.stderr.strip() or exc.stdout.strip() or str(exc)
            raise ValueError(f"post command failed ({cmd}): {details}") from exc
        if result.returncode != 0:
            raise ValueError(
                f"post command failed ({cmd}) with exit code {result.returncode}"
            )


def create_project(
    base_dir: Path,
    folder_name: str,
    add_date_prefix: bool,
    add_tmp_suffix: bool,
    copier_template: str | None = None,
    initial_tags: list[str] | None = None,
) -> Path:
    final_name = resolve_new_project_name(folder_name, add_date_prefix, add_tmp_suffix)
    target = base_dir / final_name
    if target.exists():
        raise ValueError(f"target already exists: {target}")

    target.mkdir(parents=True)

    if copier_template:
        template_dir = (base_dir / ".copier" / copier_template).resolve()
        if not template_dir.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            raise ValueError(f"template not found: {copier_template}")
        copier_yml = template_dir / "copier.yml"
        copier_yaml = template_dir / "copier.yaml"
        has_copier_config = copier_yml.is_file() or copier_yaml.is_file()

        if has_copier_config:
            if shutil.which("copier") is None:
                shutil.rmtree(target, ignore_errors=True)
                raise ValueError("copier is not installed")
            try:
                subprocess.run(
                    ["copier", "copy", "--trust", str(template_dir), str(target)],
                    check=True,
                    text=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as exc:
                shutil.rmtree(target, ignore_errors=True)
                details = exc.stderr.strip() or exc.stdout.strip() or str(exc)
                raise ValueError(f"copier failed: {details}") from exc
        else:
            try:
                scaffold_template_directory(template_dir, target)
            except (OSError, ValueError):
                shutil.rmtree(target, ignore_errors=True)
                raise

    ensure_base_marker(target)
    tags_to_write = sorted({t.strip() for t in (initial_tags or []) if t.strip()})
    if tags_to_write:
        save_base_tags(base_dir, target, tags_to_write)

    return target


def cmd_new(base_dir: Path) -> int:
    from ..cache.api import cache_upsert_project_fast
    from ..tmux.flow import open_shell_in_dir
    from ..ui import run_textual_ui

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("b new requires an interactive terminal", file=sys.stderr)
        return 1
    try:
        action, path, post_commands = run_textual_ui(
            base_dir, Path.cwd().resolve(), start_new=True
        )
    except KeyboardInterrupt:
        print()
        return 130
    if action == "open" and path:
        cache_upsert_project_fast(base_dir, path)
        try:
            run_post_commands(path, post_commands)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return open_shell_in_dir(path)
    if action == "new" and path:
        cache_upsert_project_fast(base_dir, path)
        try:
            run_post_commands(path, post_commands)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"created: {path}")
        return 0
    return 1


def git_info(path: Path, include_dirty: bool = True) -> tuple[str, str, int]:
    if not (path / ".git").is_dir():
        return "-", "-", 0
    try:
        branch = (
            core_utils.run_out("git", "-C", str(path), "branch", "--show-current") or "(detached)"
        )
    except (subprocess.SubprocessError, OSError, ValueError):
        branch = "?"
    if include_dirty:
        try:
            p1 = subprocess.run(
                [
                    "git",
                    "-C",
                    str(path),
                    "diff",
                    "--quiet",
                    "--ignore-submodules",
                    "--",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            p2 = subprocess.run(
                [
                    "git",
                    "-C",
                    str(path),
                    "diff",
                    "--cached",
                    "--quiet",
                    "--ignore-submodules",
                    "--",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            if p1.returncode == 0 and p2.returncode == 0:
                dirty = ""
            elif p1.returncode in {1} or p2.returncode in {1}:
                dirty = "*"
            else:
                # Fallback correctness path.
                dirty = (
                    "*"
                    if core_utils.run_out("git", "-C", str(path), "status", "--porcelain")
                    else ""
                )
        except (subprocess.SubprocessError, OSError, ValueError):
            dirty = "?"
    else:
        dirty = "~"
    try:
        git_ts_s = core_utils.run_out("git", "-C", str(path), "log", "-1", "--format=%ct")
        git_ts = int(git_ts_s) if git_ts_s else 0
    except (subprocess.SubprocessError, OSError, ValueError):
        git_ts = 0
    return branch, dirty, git_ts


def classify_name(name: str) -> tuple[bool, bool, str | None]:
    matched: str | None = None
    for suffix in SUFFIXES:
        if name.endswith(f".{suffix}"):
            matched = suffix
            break
    return matched == "fork", matched == "tmp", matched


def _path_size_bytes(path: Path) -> int:
    try:
        if path.is_file():
            return max(0, int(path.stat().st_size))
    except OSError:
        return 0

    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            root_path = Path(root)
            for name in files:
                p = root_path / name
                try:
                    total += max(0, int(p.stat().st_size))
                except OSError:
                    continue
    except OSError:
        return 0
    return total


def _resolve_row_size(
    path: Path,
    prev_size_bytes: int | None,
    prev_refresh_count: int,
    force_refresh: bool = False,
) -> tuple[int, int]:
    prev_size = int(prev_size_bytes) if prev_size_bytes is not None else -1
    prev_count = max(0, int(prev_refresh_count))
    next_count = prev_count + 1
    should_refresh = bool(force_refresh)
    if prev_size < 0:
        should_refresh = True
    if next_count % SIZE_REFRESH_EVERY_N == 0:
        should_refresh = True
    if should_refresh:
        return _path_size_bytes(path), next_count
    return max(0, prev_size), next_count


def project_row(
    path: Path,
    archived: bool = False,
    restore_target: Path | None = None,
    archived_ts: int = 0,
    include_git_dirty: bool = True,
    prev_size_bytes: int | None = None,
    prev_size_refresh_count: int = 0,
    force_size_refresh: bool = False,
) -> ProjectRow:
    st = path.stat()
    mtime_ts = int(st.st_mtime)
    created_ts = int(getattr(st, "st_birthtime", st.st_ctime))
    packed = core_utils.is_packed_archive_path(path, PACKED_ARCHIVE_SUFFIX)
    pack_format = "tgz" if packed else None
    if packed:
        branch, dirty, git_ts = "-", "", 0
    else:
        branch, dirty, git_ts = git_info(path, include_dirty=include_git_dirty)
    tags, description, wip, opened_ts = load_base_meta(path)
    properties = detect_properties(path)
    if packed:
        properties.append("pkg")
    health_level, _health_msg = base_meta_health(path)
    if health_level == "error":
        properties.append("err")
    elif health_level == "warning":
        properties.append("warn")
    properties = normalize_property_keys(properties)
    last_ts = git_ts if git_ts > 0 else mtime_ts
    src = "git" if git_ts > 0 else "fs"
    is_fork, is_tmp, suffix = classify_name(path.name)
    size_bytes, size_refresh_count = _resolve_row_size(
        path,
        prev_size_bytes,
        prev_size_refresh_count,
        force_refresh=force_size_refresh,
    )
    return ProjectRow(
        path=path,
        name=path.name,
        branch=branch,
        dirty=dirty,
        last=core_utils.fmt_ymd(last_ts),
        src=src,
        created=core_utils.fmt_ymd(created_ts),
        tags=tags,
        properties=properties,
        description=description,
        created_ts=created_ts,
        last_ts=last_ts,
        git_ts=git_ts,
        opened_ts=opened_ts,
        is_fork=is_fork,
        is_tmp=is_tmp,
        archived=archived,
        restore_target=restore_target,
        archived_ts=archived_ts,
        wip=wip,
        suffix=suffix,
        packed=packed,
        pack_format=pack_format,
        size_bytes=size_bytes,
        size_refresh_count=size_refresh_count,
    )
