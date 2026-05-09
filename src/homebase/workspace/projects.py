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
    detect_properties,
    ensure_base_marker,
    load_base_meta,
    normalize_property_keys,
    property_tokens,
    save_base_tags,
)


def build_row_haystack_lower(
    *,
    name: str,
    description: str,
    tags: list[str],
    properties: list[str],
    branch: str,
    path: Path,
) -> str:
    return " ".join(
        [
            name,
            description,
            " ".join(tags),
            " ".join(properties),
            property_tokens(properties),
            branch,
            path.as_posix(),
        ]
    ).lower()


def refresh_row_caches(row: ProjectRow) -> None:
    row.tags_lower = frozenset(str(tag).lower() for tag in row.tags)
    row.haystack_lower = build_row_haystack_lower(
        name=row.name,
        description=row.description,
        tags=row.tags,
        properties=row.properties,
        branch=row.branch,
        path=row.path,
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
                cmd,
                cwd=target_dir,
                shell=True,
                check=False,
                text=True,
                encoding="utf-8",
                errors="replace",
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
                )
            except subprocess.CalledProcessError as exc:
                shutil.rmtree(target, ignore_errors=True)
                details = f"copier exited with code {exc.returncode}"
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


def _alpha_name_at(index: int) -> str:
    n = index
    out = ""
    while True:
        n, rem = divmod(n, 26)
        out = chr(ord("a") + rem) + out
        if n == 0:
            return out
        n -= 1


def _next_available_alpha_name(
    base_dir: Path,
    *,
    add_date_prefix: bool,
    add_tmp_suffix: bool,
) -> str:
    for i in range(8192):
        candidate = _alpha_name_at(i)
        final_name = resolve_new_project_name(candidate, add_date_prefix, add_tmp_suffix)
        if not (base_dir / final_name).exists():
            return candidate
    raise ValueError("unable to find free alpha project name")


def cmd_create_quick(
    base_dir: Path,
    template_key: str,
    name: str | None = None,
    *,
    debug: bool = False,
) -> int:
    from ..cache.api import cache_upsert_project_fast
    from ..config.prefs import load_create_templates
    from ..tmux.flow import open_shell_in_dir

    entries = load_create_templates(base_dir)
    entry = next((e for e in entries if str(e.get("key", "")) == template_key), None)
    if entry is None:
        print(f"create template not found: {template_key}", file=sys.stderr)
        return 1

    options = {str(v).strip() for v in entry.get("options", []) if str(v).strip()}
    add_date_prefix = "prefix-datetime" in options
    add_tmp_suffix = "suffix-tmp" in options
    change_dir = "changedir" in options
    prompt_name = "prompt-name" in options
    generate_ts_name = "generate-ts-name" in options
    generate_next_alpha_name = "generate-next-alpha-name" in options

    folder_name = str(name or "").strip()
    if not folder_name and prompt_name:
        if not sys.stdin.isatty():
            print("quick create failed: prompt-name requires an interactive terminal", file=sys.stderr)
            return 1
        try:
            folder_name = input("folder name: ").strip()
        except EOFError:
            folder_name = ""
    if not folder_name and generate_ts_name:
        folder_name = datetime.now().strftime("%Y%m%d-%H%M%S")
    if not folder_name and generate_next_alpha_name:
        try:
            folder_name = _next_available_alpha_name(
                base_dir,
                add_date_prefix=add_date_prefix,
                add_tmp_suffix=add_tmp_suffix,
            )
        except ValueError as exc:
            print(f"quick create failed: {exc}", file=sys.stderr)
            return 1
    if not folder_name:
        folder_name = template_key

    template_raw = entry.get("template", None)
    copier_template = (
        str(template_raw).strip()
        if template_raw is not None and str(template_raw).strip()
        else None
    )
    initial_tags = [str(v).strip() for v in entry.get("tags", []) if str(v).strip()]

    final_name = resolve_new_project_name(folder_name, add_date_prefix, add_tmp_suffix)
    target = base_dir / final_name

    if debug:
        print("quick-create debug")
        print(f"- key: {template_key}")
        print(f"- input name: {name or '-'}")
        print(f"- resolved base name: {folder_name}")
        print(f"- final name: {final_name}")
        print(f"- target: {target}")
        print(f"- options: {sorted(options)}")
        print(f"- template: {copier_template or '-'}")
        print(f"- tags: {initial_tags}")
        print(f"- changedir: {'yes' if change_dir else 'no'}")
        print("- dry-run: no files created")
        return 0

    try:
        created = create_project(
            base_dir,
            folder_name,
            add_date_prefix,
            add_tmp_suffix,
            copier_template=copier_template,
            initial_tags=initial_tags,
        )
    except ValueError as exc:
        print(f"quick create failed: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"quick create failed: {exc}", file=sys.stderr)
        return 1

    cache_upsert_project_fast(base_dir, created)
    print(f"created: {created}")
    if change_dir and sys.stdin.isatty() and sys.stdout.isatty():
        return open_shell_in_dir(created)
    return 0


_GIT_INFO_CACHE: dict[Path, tuple[int, str, str, int, str]] = {}
_GIT_INFO_CACHE_MAX = 8192


def _resolve_head_ref_text(git_dir: Path, head_text: str) -> str:
    if not head_text.startswith("ref: "):
        return head_text
    ref_rel = head_text[5:].strip()
    if not ref_rel:
        return head_text
    ref_file = git_dir / ref_rel
    try:
        ref_sha = ref_file.read_text(encoding="utf-8", errors="replace").strip()
        if ref_sha:
            return f"{head_text}@{ref_sha}"
    except OSError:
        pass
    packed_refs = git_dir / "packed-refs"
    try:
        for line in packed_refs.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line or line[0] in {"#", "^"}:
                continue
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2 and parts[1] == ref_rel:
                return f"{head_text}@{parts[0]}"
    except OSError:
        pass
    return head_text


def _git_state_signature(git_dir: Path) -> tuple[int, str] | None:
    head_file = git_dir / "HEAD"
    index_file = git_dir / "index"
    try:
        head_text = head_file.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    try:
        index_mtime_ns = int(index_file.stat().st_mtime_ns)
    except OSError:
        index_mtime_ns = 0
    return index_mtime_ns, _resolve_head_ref_text(git_dir, head_text)


def _git_diff_quiet(path: Path, cached: bool) -> str:
    args = ["git", "-C", str(path), "diff"]
    if cached:
        args.append("--cached")
    args += ["--quiet", "--ignore-submodules", "--"]
    p = subprocess.run(
        args,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if p.returncode == 0:
        return ""
    if p.returncode == 1:
        return "*"
    return "?"


def _combine_dirty(working: str, cached_side: str) -> str:
    if working == "?" or cached_side == "?":
        return "?"
    if working == "*" or cached_side == "*":
        return "*"
    return ""


def _porcelain_dirty(path: Path) -> str:
    try:
        return (
            "*"
            if core_utils.run_out("git", "-C", str(path), "status", "--porcelain")
            else ""
        )
    except (subprocess.SubprocessError, OSError, ValueError):
        return "?"


def _git_clear_cache() -> None:
    _GIT_INFO_CACHE.clear()


def git_info(path: Path, include_dirty: bool = True) -> tuple[str, str, int]:
    git_dir = path / ".git"
    if not git_dir.is_dir():
        return "-", "-", 0

    sig = _git_state_signature(git_dir)
    cached = _GIT_INFO_CACHE.get(path) if sig is not None else None
    if (
        cached is not None
        and sig is not None
        and cached[0] == sig[0]
        and cached[1] == sig[1]
    ):
        cached_branch = cached[2]
        cached_git_ts = cached[3]
        cached_side_dirty = cached[4]
        if not include_dirty:
            return cached_branch, "~", cached_git_ts
        try:
            working_dirty = _git_diff_quiet(path, cached=False)
        except (subprocess.SubprocessError, OSError, ValueError):
            return cached_branch, "?", cached_git_ts
        if working_dirty == "?":
            return cached_branch, _porcelain_dirty(path), cached_git_ts
        return cached_branch, _combine_dirty(working_dirty, cached_side_dirty), cached_git_ts

    try:
        branch = (
            core_utils.run_out("git", "-C", str(path), "branch", "--show-current") or "(detached)"
        )
    except (subprocess.SubprocessError, OSError, ValueError):
        branch = "?"

    cached_side_dirty = ""
    if include_dirty:
        try:
            working_dirty = _git_diff_quiet(path, cached=False)
            cached_side_dirty = _git_diff_quiet(path, cached=True)
            if working_dirty == "?" or cached_side_dirty == "?":
                dirty = _porcelain_dirty(path)
            else:
                dirty = _combine_dirty(working_dirty, cached_side_dirty)
        except (subprocess.SubprocessError, OSError, ValueError):
            dirty = "?"
    else:
        dirty = "~"

    try:
        git_ts_s = core_utils.run_out("git", "-C", str(path), "log", "-1", "--format=%ct")
        git_ts = int(git_ts_s) if git_ts_s else 0
    except (subprocess.SubprocessError, OSError, ValueError):
        git_ts = 0

    if (
        sig is not None
        and branch != "?"
        and (not include_dirty or cached_side_dirty in {"", "*"})
    ):
        if len(_GIT_INFO_CACHE) >= _GIT_INFO_CACHE_MAX:
            _GIT_INFO_CACHE.clear()
        _GIT_INFO_CACHE[path] = (sig[0], sig[1], branch, git_ts, cached_side_dirty)
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
    opened_ts_override: int | None = None,
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
    tags, description, wip = load_base_meta(path)
    opened_ts = max(0, int(opened_ts_override or 0))
    properties = detect_properties(path, archived=archived)
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
    name = path.name
    haystack_lower = build_row_haystack_lower(
        name=name,
        description=description,
        tags=tags,
        properties=properties,
        branch=branch,
        path=path,
    )
    return ProjectRow(
        path=path,
        name=name,
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
        haystack_lower=haystack_lower,
    )
