from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable


def cmd_archive_mv_one(
    base_dir: Path,
    path: str,
    *,
    archive_destination: Callable[[Path, Path], Path],
    confirm: Callable[[], None],
    archive_move_internal: Callable[[Path, Path], Path],
    skip_confirm: bool = False,
) -> int:
    src = Path(path).resolve()
    dest = archive_destination(src, base_dir)
    print(f"archive: {src}")
    print(f"     -> {dest}")
    if not skip_confirm:
        confirm()
    try:
        archive_move_internal(base_dir, src)
        print("done")
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def cmd_archive_mv(
    base_dir: Path,
    path: str,
    *,
    archive_destination: Callable[[Path, Path], Path],
    confirm: Callable[[], None],
    archive_move_internal: Callable[[Path, Path], Path],
) -> int:
    return cmd_archive_mv_one(
        base_dir,
        path,
        archive_destination=archive_destination,
        confirm=confirm,
        archive_move_internal=archive_move_internal,
    )


def cmd_archive_ls(
    base_dir: Path,
    path: str,
    *,
    policy_reason_outside_base: Callable[[Path, Path], str | None],
    archive_root: Callable[[Path], Path],
) -> int:
    src = Path(path).resolve()
    if policy_reason_outside_base(src, base_dir):
        print(f"path not under base: {src}", file=sys.stderr)
        return 1
    root = archive_root(base_dir)
    if not root.is_dir():
        print("no archives found")
        return 0
    name = src.name
    matches = sorted(
        list(root.glob(f"*/*_{name}"))
        + list(root.glob(f"*/*_{name}.tgz"))
    )
    if not matches:
        print("no archives found")
        return 0
    print(f"{root}/")
    for match in matches:
        print(match.relative_to(root))
    return 0


def cmd_archive_restore_entry(
    base_dir: Path,
    archived_path: str,
    *,
    archived_restore_target: Callable[[Path, Path], Path],
    confirm: Callable[[], None],
    archive_restore_internal: Callable[[Path, Path], Path],
) -> int:
    src = Path(archived_path).resolve()
    target = archived_restore_target(base_dir, src)
    print(f"restore: {src}")
    print(f"     -> {target}")
    confirm()
    try:
        archive_restore_internal(base_dir, src)
        print("done")
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def cmd_archive_undo(
    base_dir: Path,
    path: str,
    *,
    policy_reason_outside_base: Callable[[Path, Path], str | None],
    archive_root: Callable[[Path], Path],
    cmd_archive_restore_entry: Callable[[Path, str], int],
) -> int:
    src = Path(path).resolve()
    if policy_reason_outside_base(src, base_dir):
        print(f"path not under base: {src}", file=sys.stderr)
        return 1
    root = archive_root(base_dir)
    name = src.name
    candidates = sorted(
        list(root.glob(f"*/*_{name}"))
        + list(root.glob(f"*/*_{name}.tgz")),
        reverse=True,
    )
    if not candidates:
        print(f"no archives found for: {name}", file=sys.stderr)
        return 1
    return cmd_archive_restore_entry(base_dir, str(candidates[0]))


def cmd_rm(
    path: str,
    *,
    env_base_dir_key: str,
    policy_reason_outside_base: Callable[[Path, Path], str | None],
    prompt_yes_no: Callable[[str, bool], bool],
    delete_internal: Callable[[Path, Path], None],
    force_outside_base: bool,
    force: bool = False,
) -> int:
    target = Path(path).resolve()
    base_dir = Path(os.environ.get(env_base_dir_key, ".")).resolve()
    if target == base_dir:
        print(f"refusing to delete base directory: {base_dir}", file=sys.stderr)
        return 1
    if not force_outside_base and policy_reason_outside_base(target, base_dir):
        print(f"refusing to delete outside base (use --force-outside-base): {target}", file=sys.stderr)
        return 1
    if not force:
        if not prompt_yes_no(f"delete: {target}", False):
            print("aborted")
            return 1
    try:
        delete_internal(base_dir, target)
        print(f"deleted: {target}")
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def suggest_project_root(path: Path) -> Path:
    current = path
    while True:
        try:
            entries = [entry for entry in current.iterdir() if not entry.name.startswith(".")]
        except OSError:
            break
        dirs = [entry for entry in entries if entry.is_dir()]
        files = [entry for entry in entries if entry.is_file()]
        if len(dirs) == 1 and not files:
            current = dirs[0]
            continue
        break
    return current


def find_marker_root_upward(path: Path, marker_file: str) -> Path | None:
    cur = path.resolve()
    while True:
        if (cur / marker_file).is_file():
            return cur
        parent = cur.parent
        if parent == cur:
            return None
        cur = parent


FIX_MARKER = "marker"
FIX_ARCHIVE_ENTRY = "archive-entry"
FIX_KINDS: tuple[str, ...] = (FIX_MARKER, FIX_ARCHIVE_ENTRY)


def _is_year_dir(name: str, archive_year_re) -> bool:
    return bool(archive_year_re.match(name))


_CANONICAL_ENTRY_NAME_RE = re.compile(
    r"^(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])_.+$"
)


def _archive_entry_stem_name(name: str) -> str:
    """Strip the ``.tgz`` suffix when classifying an archive entry —
    canonical naming rules apply to the bare stem either way."""
    return name[:-4] if name.endswith(".tgz") else name


def _is_archive_entry_candidate(entry: Path) -> bool:
    """Either a directory or a packed ``.tgz`` archive sitting inside
    ``_archive``."""
    if entry.is_dir():
        return True
    if entry.is_file() and entry.name.endswith(".tgz"):
        return True
    return False


def _is_canonical_archive_entry(entry: Path, year_dir_name: str) -> bool:
    """An archive entry is canonical when it lives at
    ``_archive/<year>/<YYYY-MM-DD>_<stem>`` and the date matches its
    parent year directory."""
    bare = _archive_entry_stem_name(entry.name)
    m = _CANONICAL_ENTRY_NAME_RE.match(bare)
    if not m:
        return False
    return m.group(1) == year_dir_name


def _list_archive_root_fixables(
    root: Path,
    archive_year_re,
) -> list[Path]:
    """Items under ``_archive`` that need fixing:

    - Direct children (dirs or ``.tgz`` files) that aren't year dirs
      — legacy malformed entries sitting at the top level.
    - Children inside year dirs whose name isn't canonical
      ``YYYY-MM-DD_<stem>`` or whose embedded year doesn't match the
      parent year directory.

    Dotfile/underscore-prefixed entries are skipped.
    """
    out: list[Path] = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return out
    for entry in entries:
        if entry.name.startswith(".") or entry.name.startswith("_"):
            continue
        if entry.is_dir() and _is_year_dir(entry.name, archive_year_re):
            try:
                year_children = sorted(entry.iterdir())
            except OSError:
                continue
            for child in year_children:
                if child.name.startswith(".") or child.name.startswith("_"):
                    continue
                if not _is_archive_entry_candidate(child):
                    continue
                if _is_canonical_archive_entry(child, entry.name):
                    continue
                out.append(child)
            continue
        if not _is_archive_entry_candidate(entry):
            continue
        out.append(entry)
    return out


def _ask_for_archive_date(
    target: Path,
    *,
    yes: bool,
    archive_tz,
    read_line: Callable[[str], str | None],
    parse_user_date: Callable[[str, object], int | None],
    max_attempts: int = 3,
) -> tuple[int, str] | None:
    """Resolve a date when detection has failed. Returns (ts, source)
    or None on abort."""
    today_dt = datetime.now(archive_tz)
    today_iso = today_dt.strftime("%Y-%m-%d")
    today_ts = int(today_dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    if yes or not sys.stdin.isatty():
        return today_ts, f"today ({today_iso}) — fallback"
    for _ in range(max_attempts):
        raw = read_line(
            f"  date for '{target.name}' [YYYY-MM-DD, default {today_iso}]: "
        )
        if raw is None:
            return None
        text = raw.strip()
        if not text:
            return today_ts, f"today ({today_iso})"
        parsed = parse_user_date(text, archive_tz)
        if parsed is not None:
            return parsed, f"user input {text}"
        print("  invalid date format, expected YYYY-MM-DD", file=sys.stderr)
    print("  giving up: no valid date", file=sys.stderr)
    return None


def _fix_archive_entry(
    target: Path,
    *,
    archive_root: Path,
    include: set[str],
    yes: bool,
    archive_tz,
    parse_archive_timestamp: Callable[[str], int],
    archive_iso_from_ts: Callable[[int, object], str],
    detect_folder_date,
    parse_user_date: Callable[[str, object], int | None],
    strip_date_prefix: Callable[[str], str],
    prompt_yes_no: Callable[[str, bool], bool],
    read_line: Callable[[str], str | None],
) -> int:
    print(f"fix archive entry: {target}")
    if FIX_ARCHIVE_ENTRY not in include:
        print("archive-entry: skipped (--no-archive-entry)")
        return 0

    detection = detect_folder_date(
        target,
        parse_timestamp=parse_archive_timestamp,
        archive_tz=archive_tz,
    )
    if detection is not None:
        ts = detection.ts
        source = detection.source
    else:
        resolved = _ask_for_archive_date(
            target,
            yes=yes,
            archive_tz=archive_tz,
            read_line=read_line,
            parse_user_date=parse_user_date,
        )
        if resolved is None:
            print("aborted: no valid date", file=sys.stderr)
            return 1
        ts, source = resolved

    iso = archive_iso_from_ts(ts, archive_tz)
    date_prefix = iso[:10]
    year = date_prefix[:4]
    stem = strip_date_prefix(target.name)
    if not stem:
        stem = target.name
    canonical_name = f"{date_prefix}_{stem}"
    canonical_path = (archive_root / year / canonical_name).resolve()

    if canonical_path == target:
        print(f"already canonical: {target.name} ({source})")
        return 0
    print(f"  date source: {source}")
    print(f"  move: {target}")
    print(f"     -> {canonical_path}")
    if canonical_path.exists():
        print(
            f"  refusing: destination exists: {canonical_path}",
            file=sys.stderr,
        )
        return 1
    if not yes:
        if not prompt_yes_no("apply rename/move?", True):
            print("  aborted")
            return 1
    try:
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        target.rename(canonical_path)
    except OSError as exc:
        print(f"  move failed: {exc}", file=sys.stderr)
        return 1
    print(f"  done: {canonical_path}")
    return 0


def _fix_active_project(
    target: Path,
    *,
    include: set[str],
    yes: bool,
    base_marker_file: str,
    prompt_yes_no: Callable[[str, bool], bool],
    ensure_base_marker: Callable[[Path], None],
    confirm: Callable[[], None],
) -> int:
    print(f"fix project: {target}")
    if FIX_MARKER not in include:
        print("marker: skipped (--no-marker)")
        return 0
    marker_file = target / base_marker_file
    if marker_file.exists():
        print(f"marker: exists ({marker_file.name})")
        return 0
    create = yes or prompt_yes_no(
        f"create {base_marker_file} in {target}?", True
    )
    if not create:
        print("marker: skipped (declined)")
        return 0
    if not yes:
        confirm()
    try:
        ensure_base_marker(target)
    except OSError as exc:
        print(f"  marker create failed: {exc}", file=sys.stderr)
        return 1
    print(f"  created: {marker_file}")
    return 0


def _fix_one(
    raw_path: str,
    *,
    include: set[str],
    yes: bool,
    base_dir: Path,
    archive_dir_name: str,
    archive_year_re,
    archive_tz,
    is_under: Callable[[Path, Path], bool],
    base_marker_file: str,
    prompt_yes_no: Callable[[str, bool], bool],
    parse_archive_timestamp: Callable[[str], int],
    archive_iso_from_ts: Callable[[int, object], str],
    detect_folder_date,
    parse_user_date: Callable[[str, object], int | None],
    strip_date_prefix: Callable[[str], str],
    ensure_base_marker: Callable[[Path], None],
    confirm: Callable[[], None],
    read_line: Callable[[str], str | None],
) -> int:
    target = Path(raw_path).expanduser().resolve()
    if not target.exists():
        print(f"skipping: not found ({target})", file=sys.stderr)
        return 0
    if not is_under(target, base_dir) and target != base_dir:
        print(
            f"skipping: not under base ({base_dir}): {target}",
            file=sys.stderr,
        )
        return 0

    archive_root = (base_dir / archive_dir_name).resolve()
    in_archive_subtree = is_under(target, archive_root)
    is_packed_archive_file = (
        target.is_file()
        and target.name.endswith(".tgz")
        and in_archive_subtree
    )
    if not target.is_dir() and not is_packed_archive_file:
        print(f"skipping: not a directory ({target})", file=sys.stderr)
        return 0

    # ``b fix _archive`` — fan out to every malformed entry, including
    # those inside year subdirs.
    if target == archive_root:
        fixables = _list_archive_root_fixables(archive_root, archive_year_re)
        if not fixables:
            print("nothing to fix under _archive")
            return 0
        print(f"fanning out {len(fixables)} entry/entries under _archive")
        worst = 0
        for child in fixables:
            print("")
            rc = _fix_archive_entry(
                child,
                archive_root=archive_root,
                include=include,
                yes=yes,
                archive_tz=archive_tz,
                parse_archive_timestamp=parse_archive_timestamp,
                archive_iso_from_ts=archive_iso_from_ts,
                detect_folder_date=detect_folder_date,
                parse_user_date=parse_user_date,
                strip_date_prefix=strip_date_prefix,
                prompt_yes_no=prompt_yes_no,
                read_line=read_line,
            )
            if rc != 0 and (worst == 0 or rc > worst):
                worst = rc
        return worst

    # Anything under ``_archive``.
    if is_under(target, archive_root):
        try:
            rel_parts = target.relative_to(archive_root).parts
        except ValueError:
            rel_parts = ()
        if len(rel_parts) == 1:
            # ``_archive/<X>``: either a year dir (skip) or a legacy
            # malformed entry sitting at the top level (fix).
            if _is_year_dir(rel_parts[0], archive_year_re):
                print(
                    f"skipping: year directory has no fix at this level ({target})"
                )
                return 0
            return _fix_archive_entry(
                target,
                archive_root=archive_root,
                include=include,
                yes=yes,
                archive_tz=archive_tz,
                parse_archive_timestamp=parse_archive_timestamp,
                archive_iso_from_ts=archive_iso_from_ts,
                detect_folder_date=detect_folder_date,
                parse_user_date=parse_user_date,
                strip_date_prefix=strip_date_prefix,
                prompt_yes_no=prompt_yes_no,
                read_line=read_line,
            )
        if len(rel_parts) == 2 and _is_year_dir(rel_parts[0], archive_year_re):
            # Canonical position: ``_archive/<year>/<entry>``.
            return _fix_archive_entry(
                target,
                archive_root=archive_root,
                include=include,
                yes=yes,
                archive_tz=archive_tz,
                parse_archive_timestamp=parse_archive_timestamp,
                archive_iso_from_ts=archive_iso_from_ts,
                detect_folder_date=detect_folder_date,
                parse_user_date=parse_user_date,
                strip_date_prefix=strip_date_prefix,
                prompt_yes_no=prompt_yes_no,
                read_line=read_line,
            )
        print(
            f"skipping: not a fixable archive target ({target})",
            file=sys.stderr,
        )
        return 0

    # Outside ``_archive``: must be a direct base entry, not reserved.
    if target == base_dir:
        print(
            f"skipping: pass a project path, not base itself ({target})",
            file=sys.stderr,
        )
        return 0
    if target.parent != base_dir:
        print(
            f"skipping: not a direct base entry ({target})",
            file=sys.stderr,
        )
        return 0
    if target.name.startswith("_") or target.name.startswith("."):
        print(f"skipping: reserved directory ({target})")
        return 0

    return _fix_active_project(
        target,
        include=include,
        yes=yes,
        base_marker_file=base_marker_file,
        prompt_yes_no=prompt_yes_no,
        ensure_base_marker=ensure_base_marker,
        confirm=confirm,
    )


def _collect_all_targets(base_dir: Path, archive_dir_name: str) -> list[str]:
    """``--all`` expansion: every direct base project plus the
    ``_archive`` root (which the inner pipeline fans out further).
    Hidden / underscore entries are skipped."""
    out: list[str] = []
    try:
        entries = sorted(base_dir.iterdir())
    except OSError:
        entries = []
    for entry in entries:
        if entry.name.startswith(".") or entry.name.startswith("_"):
            continue
        if entry.is_dir():
            out.append(str(entry))
    archive_root = base_dir / archive_dir_name
    if archive_root.is_dir():
        out.append(str(archive_root))
    return out


def cmd_fix(
    paths: list[str],
    *,
    include: set[str],
    yes: bool,
    env_base_dir_key: str,
    archive_dir_name: str,
    archive_year_re,
    archive_tz,
    is_under: Callable[[Path, Path], bool],
    base_marker_file: str,
    prompt_yes_no: Callable[[str, bool], bool],
    parse_archive_timestamp: Callable[[str], int],
    archive_iso_from_ts: Callable[[int, object], str],
    detect_folder_date,
    parse_user_date: Callable[[str, object], int | None],
    strip_date_prefix: Callable[[str], str],
    ensure_base_marker: Callable[[Path], None],
    confirm: Callable[[], None],
    read_line: Callable[[str], str | None],
    all_targets: bool = False,
) -> int:
    if not include:
        print("fix: no fixers selected", file=sys.stderr)
        return 2
    base_dir = Path(os.environ.get(env_base_dir_key, ".")).resolve()
    if all_targets:
        if paths:
            print(
                "note: --all overrides explicit paths",
                file=sys.stderr,
            )
        targets = _collect_all_targets(base_dir, archive_dir_name)
        if not targets:
            print("nothing to sweep under base")
            return 0
    else:
        targets = list(paths) if paths else ["."]
    worst: int = 0
    for idx, raw in enumerate(targets):
        if idx > 0:
            print("")
        if len(targets) > 1:
            print(f"== {raw} ==")
        rc = _fix_one(
            raw,
            include=include,
            yes=yes,
            base_dir=base_dir,
            archive_dir_name=archive_dir_name,
            archive_year_re=archive_year_re,
            archive_tz=archive_tz,
            is_under=is_under,
            base_marker_file=base_marker_file,
            prompt_yes_no=prompt_yes_no,
            parse_archive_timestamp=parse_archive_timestamp,
            archive_iso_from_ts=archive_iso_from_ts,
            detect_folder_date=detect_folder_date,
            parse_user_date=parse_user_date,
            strip_date_prefix=strip_date_prefix,
            ensure_base_marker=ensure_base_marker,
            confirm=confirm,
            read_line=read_line,
        )
        if rc != 0 and (worst == 0 or rc > worst):
            worst = rc
    return worst
