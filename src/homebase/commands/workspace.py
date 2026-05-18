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


# ---- display helpers for ``b fix`` ----------------------------------
# ANSI styling: only emit when stdout is a real TTY so pytest capture
# and pipe redirection stay plain text.


def _fix_colors_on() -> bool:
    try:
        return sys.stdout.isatty()
    except (OSError, ValueError):
        return False


def _c(text: object, code: str) -> str:
    s = str(text)
    if not _fix_colors_on():
        return s
    return f"\x1b[{code}m{s}\x1b[0m"


def _bold(t: object) -> str: return _c(t, "1")
def _dim(t: object) -> str: return _c(t, "2")
def _red(t: object) -> str: return _c(t, "31")
def _green(t: object) -> str: return _c(t, "32")
def _yellow(t: object) -> str: return _c(t, "33")
def _cyan(t: object) -> str: return _c(t, "36")
def _b_yellow(t: object) -> str: return _c(t, "1;33")
def _b_cyan(t: object) -> str: return _c(t, "1;36")


_GLYPH_OK = _green("✓")
_GLYPH_INFO = _cyan("•")
_GLYPH_ACTION = _yellow("→")
_GLYPH_WARN = _yellow("⚠")
_GLYPH_FAIL = _red("✗")
_GLYPH_SKIP = _dim("—")


def _fmt_location(target: Path, base_dir: Path) -> str:
    """A short hint shown next to the entry name in the header line."""
    if target == base_dir:
        return "base"
    try:
        rel = target.parent.relative_to(base_dir)
    except ValueError:
        return ""
    s = str(rel)
    return "" if s == "." else s


def _print_item_header(
    idx: int, total: int, name: str, location: str,
) -> None:
    counter = _b_yellow(f"[{idx}/{total}]")
    label = _bold(name)
    if location:
        print(f"\n{counter} {label}  {_dim(location)}")
    else:
        print(f"\n{counter} {label}")


def _print_top_header(base_dir: Path, total: int, all_targets: bool) -> None:
    tag = " --all" if all_targets else ""
    print(_b_cyan(f"fix{tag}: {base_dir}") + _dim(f"  ({total} item(s))"))


def _print_ok(message: str) -> None:
    print(f"  {_GLYPH_OK} {message}")


def _print_info(label: str, value: str = "") -> None:
    if value:
        print(f"  {_GLYPH_INFO} {label}: {_yellow(value)}")
    else:
        print(f"  {_GLYPH_INFO} {label}")


def _print_action(line: str, target: str | None = None) -> None:
    print(f"  {_GLYPH_ACTION} {line}")
    if target:
        print(f"      {_dim(target)}")


def _print_skip(message: str) -> None:
    print(f"  {_GLYPH_SKIP} {_dim(message)}")


def _print_warn(message: str) -> None:
    print(f"  {_GLYPH_WARN} {message}")


def _print_fail(message: str) -> None:
    print(f"  {_GLYPH_FAIL} {message}", file=sys.stderr)


def _print_summary(counts: dict[str, int]) -> None:
    parts = [
        f"{_green(counts['ok'])} ok",
        f"{_b_yellow(counts['changed'])} changed",
        f"{_dim(counts['skipped'])} skipped",
        f"{_red(counts['failed'])} failed",
    ]
    print()
    print(_bold("done.") + "  " + "  ".join(parts))


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
    prompt = f"    {_yellow('date')} [YYYY-MM-DD, default {today_iso}]: "
    for _ in range(max_attempts):
        raw = read_line(prompt)
        if raw is None:
            return None
        text = raw.strip()
        if not text:
            return today_ts, f"today ({today_iso})"
        parsed = parse_user_date(text, archive_tz)
        if parsed is not None:
            return parsed, f"user input {text}"
        _print_warn("invalid date, expected YYYY-MM-DD")
    _print_fail("giving up: no valid date provided")
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
) -> str:
    """Returns one of: 'ok' | 'changed' | 'skipped' | 'failed'."""
    if FIX_ARCHIVE_ENTRY not in include:
        _print_skip("archive-entry fixer disabled (--no-archive-entry)")
        return "skipped"

    detection = detect_folder_date(
        target,
        parse_timestamp=parse_archive_timestamp,
        archive_tz=archive_tz,
    )
    if detection is not None:
        ts = detection.ts
        source = detection.source
    else:
        _print_warn("no date found in name or content")
        resolved = _ask_for_archive_date(
            target,
            yes=yes,
            archive_tz=archive_tz,
            read_line=read_line,
            parse_user_date=parse_user_date,
        )
        if resolved is None:
            return "skipped"
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
        _print_ok(f"already canonical ({source})")
        return "ok"
    _print_info("date", f"{date_prefix}  ({source})")
    _print_action(f"rename → {canonical_name}", f"_archive/{year}/")
    if canonical_path.exists():
        _print_fail(f"destination already exists: {canonical_path}")
        return "failed"
    if not yes:
        if not prompt_yes_no(f"    {_bold('apply')}?", True):
            _print_skip("declined")
            return "skipped"
    try:
        canonical_path.parent.mkdir(parents=True, exist_ok=True)
        target.rename(canonical_path)
    except OSError as exc:
        _print_fail(f"move failed: {exc}")
        return "failed"
    _print_ok(f"moved to {canonical_path}")
    return "changed"


def _fix_active_project(
    target: Path,
    *,
    include: set[str],
    yes: bool,
    base_marker_file: str,
    prompt_yes_no: Callable[[str, bool], bool],
    ensure_base_marker: Callable[[Path], None],
) -> str:
    """Returns one of: 'ok' | 'changed' | 'skipped' | 'failed'."""
    if FIX_MARKER not in include:
        _print_skip("marker fixer disabled (--no-marker)")
        return "skipped"
    marker_file = target / base_marker_file
    if marker_file.exists():
        _print_ok(f"marker present ({base_marker_file})")
        return "ok"
    _print_warn(f"missing marker: {base_marker_file}")
    if not yes:
        if not prompt_yes_no(f"    {_bold('create')} {base_marker_file}?", True):
            _print_skip("declined")
            return "skipped"
    try:
        ensure_base_marker(target)
    except OSError as exc:
        _print_fail(f"create failed: {exc}")
        return "failed"
    _print_ok(f"created {marker_file.name}")
    return "changed"


def _expand_target(
    raw_path: str,
    *,
    base_dir: Path,
    archive_dir_name: str,
    archive_year_re,
    is_under: Callable[[Path, Path], bool],
) -> tuple[str, Path | list[Path] | None, str | None]:
    """Resolve a raw user input into a category + payload.

    Returns ``(kind, payload, reason)``:
      - ("project", path, None)     → active base project, run marker fixer
      - ("entry", path, None)       → archive entry, run archive-entry fixer
      - ("sweep", [paths], None)    → ``_archive`` itself: fan out
      - ("noop", None, reason_str)  → skip with a message
    """
    target = Path(raw_path).expanduser().resolve()
    if not target.exists():
        return "noop", None, f"not found: {target}"
    if not is_under(target, base_dir) and target != base_dir:
        return "noop", None, f"not under base: {target}"

    archive_root = (base_dir / archive_dir_name).resolve()
    in_archive = is_under(target, archive_root)
    is_packed = (
        target.is_file() and target.name.endswith(".tgz") and in_archive
    )
    if not target.is_dir() and not is_packed:
        return "noop", None, f"not a directory: {target}"

    if target == archive_root:
        fixables = _list_archive_root_fixables(archive_root, archive_year_re)
        return "sweep", fixables, None

    if in_archive:
        try:
            parts = target.relative_to(archive_root).parts
        except ValueError:
            parts = ()
        if len(parts) == 1:
            if _is_year_dir(parts[0], archive_year_re):
                return "noop", None, f"year directory: {target}"
            return "entry", target, None
        if len(parts) == 2 and _is_year_dir(parts[0], archive_year_re):
            return "entry", target, None
        return "noop", None, f"not a fixable archive target: {target}"

    if target == base_dir:
        return "noop", None, "pass a project path, not base itself"
    if target.parent != base_dir:
        return "noop", None, f"not a direct base entry: {target}"
    if target.name.startswith("_") or target.name.startswith("."):
        return "noop", None, f"reserved directory: {target.name}"

    return "project", target, None


def _process_target(
    target: Path,
    kind: str,
    *,
    base_dir: Path,
    archive_dir_name: str,
    include: set[str],
    yes: bool,
    archive_tz,
    parse_archive_timestamp: Callable[[str], int],
    archive_iso_from_ts: Callable[[int, object], str],
    detect_folder_date,
    parse_user_date: Callable[[str, object], int | None],
    strip_date_prefix: Callable[[str], str],
    prompt_yes_no: Callable[[str, bool], bool],
    base_marker_file: str,
    ensure_base_marker: Callable[[Path], None],
    read_line: Callable[[str], str | None],
) -> str:
    if kind == "entry":
        archive_root = (base_dir / archive_dir_name).resolve()
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
    return _fix_active_project(
        target,
        include=include,
        yes=yes,
        base_marker_file=base_marker_file,
        prompt_yes_no=prompt_yes_no,
        ensure_base_marker=ensure_base_marker,
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
    read_line: Callable[[str], str | None],
    all_targets: bool = False,
) -> int:
    if not include:
        print("fix: no fixers selected", file=sys.stderr)
        return 2
    base_dir = Path(os.environ.get(env_base_dir_key, ".")).resolve()
    if all_targets:
        if paths:
            print(_dim("note: --all overrides explicit paths"), file=sys.stderr)
        raw_targets = _collect_all_targets(base_dir, archive_dir_name)
        if not raw_targets:
            print("nothing to sweep under base")
            return 0
    else:
        raw_targets = list(paths) if paths else ["."]

    # First pass: classify each top-level target and flatten any
    # ``_archive`` sweeps so the final list is a flat sequence of
    # items to process. Skip notes are stashed as ``("noop", reason)``
    # so we can render them in order.
    flat: list[tuple[str, object]] = []
    for raw in raw_targets:
        kind, payload, reason = _expand_target(
            raw,
            base_dir=base_dir,
            archive_dir_name=archive_dir_name,
            archive_year_re=archive_year_re,
            is_under=is_under,
        )
        if kind == "noop":
            flat.append(("noop", reason or "skipped"))
            continue
        if kind == "sweep":
            entries = payload or []
            if not entries:
                flat.append(("noop", "nothing to fix under _archive"))
                continue
            for entry in entries:
                flat.append(("entry", entry))
            continue
        flat.append((kind, payload))

    total = len(flat)
    _print_top_header(base_dir, total, all_targets)

    counts = {"ok": 0, "changed": 0, "skipped": 0, "failed": 0}
    for idx, (kind, payload) in enumerate(flat, start=1):
        if kind == "noop":
            _print_item_header(idx, total, _dim("(skipped)"), "")
            _print_skip(str(payload))
            counts["skipped"] += 1
            continue
        target = payload
        assert isinstance(target, Path)
        location = _fmt_location(target, base_dir)
        _print_item_header(idx, total, target.name, location)
        result = _process_target(
            target,
            kind,
            base_dir=base_dir,
            archive_dir_name=archive_dir_name,
            include=include,
            yes=yes,
            archive_tz=archive_tz,
            parse_archive_timestamp=parse_archive_timestamp,
            archive_iso_from_ts=archive_iso_from_ts,
            detect_folder_date=detect_folder_date,
            parse_user_date=parse_user_date,
            strip_date_prefix=strip_date_prefix,
            prompt_yes_no=prompt_yes_no,
            base_marker_file=base_marker_file,
            ensure_base_marker=ensure_base_marker,
            read_line=read_line,
        )
        counts[result] = counts.get(result, 0) + 1

    _print_summary(counts)
    return 1 if counts["failed"] else 0
