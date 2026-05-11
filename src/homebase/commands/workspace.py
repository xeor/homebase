from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable


def cmd_archive_reorganize(
    base_dir: Path,
    *,
    archive_dir_name: str,
    year_from_name: Callable[[str], str | None],
    is_year_dir: Callable[[str], bool],
    normalize_name: Callable[[str], str],
    confirm: Callable[[], None],
    dry_run: bool,
) -> int:
    root = base_dir / archive_dir_name
    if not root.is_dir():
        print(f"no archive dir: {root}")
        return 0

    moves: list[tuple[Path, Path, bool]] = []
    skipped: list[tuple[Path, str]] = []

    def _plan(entry: Path) -> None:
        name = entry.name
        year = year_from_name(name)
        if year is None:
            skipped.append((entry, "no year prefix"))
            return
        new_name = normalize_name(name)
        renamed = new_name != name
        dest = root / year / new_name
        if dest == entry:
            return
        if dest.exists():
            skipped.append((entry, f"destination exists: {dest}"))
            return
        moves.append((entry, dest, renamed))

    for entry in sorted(root.iterdir()):
        if is_year_dir(entry.name) and entry.is_dir():
            for child in sorted(entry.iterdir()):
                _plan(child)
            continue
        _plan(entry)

    print(f"archive root: {root}")
    print(f"moves: {len(moves)}")
    for src, dest, renamed in moves:
        tag = " [normalized 00→01]" if renamed else ""
        print(f"  {src.name} -> {dest.relative_to(root)}{tag}")
    if skipped:
        print("")
        print(f"skipped: {len(skipped)}")
        for src, reason in skipped:
            print(f"  {src.name}: {reason}")
    if not moves:
        return 0
    if dry_run:
        print("")
        print("dry-run: no changes made")
        return 0

    print("")
    confirm()
    moved = 0
    failed = 0
    for src, dest, _renamed in moves:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            moved += 1
            print(f"moved: {src.name} -> {dest.relative_to(root)}")
        except (OSError, shutil.Error) as exc:
            failed += 1
            print(f"failed: {src} -> {dest}: {exc}", file=sys.stderr)
    print("")
    print(f"done: moved={moved} failed={failed}")
    return 0 if failed == 0 else 1


def cmd_archive_mv(
    base_dir: Path,
    path: str,
    *,
    archive_destination: Callable[[Path, Path], Path],
    confirm: Callable[[], None],
    archive_move_internal: Callable[[Path, Path], Path],
) -> int:
    src = Path(path).resolve()
    dest = archive_destination(src, base_dir)
    print(f"archive: {src}")
    print(f"     -> {dest}")
    confirm()
    try:
        archive_move_internal(base_dir, src)
        print("done")
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


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
    confirm: Callable[[], None],
    delete_internal: Callable[[Path, Path], None],
    force_outside_base: bool,
) -> int:
    target = Path(path).resolve()
    base_dir = Path(os.environ.get(env_base_dir_key, ".")).resolve()
    if target == base_dir:
        print(f"refusing to delete base directory: {base_dir}", file=sys.stderr)
        return 1
    if not force_outside_base and policy_reason_outside_base(target, base_dir):
        print(f"refusing to delete outside base (use --force-outside-base): {target}", file=sys.stderr)
        return 1
    print(f"delete: {target}")
    confirm()
    try:
        delete_internal(base_dir, target)
        print("done")
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def cmd_migrate(
    paths: list[str],
    *,
    archive_dir_name: str,
    split_archive_name: Callable[[str], tuple[str, int]],
    archive_destination: Callable[[Path, Path], Path],
    ensure_safe_cwd: Callable[[Path, Path], None],
    ensure_base_marker: Callable[[Path], None],
    append_base_log: Callable[[Path, str, dict[str, object]], None],
    sync_tag_symlinks: Callable[[Path], str | None],
    confirm: Callable[[], None],
    archive_mode: bool,
) -> int:
    if not paths:
        print("usage: b migrate [--archive] <path> [path ...]", file=sys.stderr)
        return 1

    target_root = (Path.home() / "base").resolve()
    archive_root = target_root / archive_dir_name
    plans: list[tuple[Path, Path, bool, list[tuple[str, str]]]] = []
    blocked: list[str] = []

    use_color = sys.stdout.isatty()
    c_reset = "\033[0m" if use_color else ""
    c_green = "\033[38;5;114m" if use_color else ""
    c_yellow = "\033[38;5;228m" if use_color else ""
    c_red = "\033[38;5;217m" if use_color else ""

    def color(level: str, text: str) -> str:
        if not use_color:
            return text
        if level == "pos":
            return f"{c_green}{text}{c_reset}"
        if level == "warn":
            return f"{c_yellow}{text}{c_reset}"
        return f"{c_red}{text}{c_reset}"

    def notes_suffix(notes: list[tuple[str, str]]) -> str:
        if not notes:
            return ""
        rendered = ", ".join(color(level, label) for level, label in notes)
        return f" ({rendered})"

    seen_src: set[Path] = set()
    seen_dest: set[Path] = set()

    for raw in paths:
        src = Path(raw).expanduser().resolve()
        notes: list[tuple[str, str]] = []
        if src in seen_src:
            blocked.append(f"duplicate source: {src}")
            continue
        seen_src.add(src)
        if not src.exists():
            blocked.append(f"not found: {src}")
            continue
        is_dir = src.is_dir()
        if not archive_mode and not is_dir:
            blocked.append(f"not a directory: {src}")
            continue
        if archive_mode and not is_dir:
            notes.append(("warn", "SOURCE_IS_FILE"))

        if archive_mode:
            _stem, parsed_ts = split_archive_name(src.name)
            if parsed_ts > 0:
                notes.append(("pos", "PARSED_EXISTING_TS"))
            dest = archive_destination(src, target_root)
        else:
            dest = target_root / src.name

        if dest in seen_dest:
            blocked.append(f"duplicate destination name: {dest.name}")
            continue
        seen_dest.add(dest)
        if src == dest:
            blocked.append(f"already at destination: {src}")
            continue
        if dest.exists():
            blocked.append(f"destination exists: {dest}")
            continue
        plans.append((src, dest, is_dir, notes))

    if blocked:
        print("blocked items:")
        for err in blocked:
            print(f"  - {color('err', err)}")
        print("")
    if not plans:
        print("nothing to migrate", file=sys.stderr)
        return 1

    print("migration plan:")
    print(f"mode: {'archive' if archive_mode else 'active'}")
    print(f"migrate to: {archive_root if archive_mode else target_root}")
    print(f"items to move: {len(plans)}")
    print("")
    print("moves:")
    for src, dest, is_dir, notes in plans:
        if is_dir:
            notes = [*notes, ("pos", "WILL_CREATE_BASE_MARKER")]
        print(f"  - {src} -> {dest}{notes_suffix(notes)}")
    print("")

    confirm()
    (archive_root if archive_mode else target_root).mkdir(parents=True, exist_ok=True)
    moved = 0
    failed = 0
    print("")
    print("executing:")
    for src, dest, is_dir, notes in plans:
        try:
            ensure_safe_cwd(target_root, src)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            if is_dir:
                ensure_base_marker(dest)
                append_base_log(
                    dest,
                    "migration",
                    {
                        "source": str(src),
                        "destination": str(dest),
                        "archive": archive_mode,
                        "source_type": "directory",
                        "signals": [label for _level, label in notes],
                    },
                )
            moved += 1
            print(f"moved: {src} -> {dest}")
        except (OSError, shutil.Error, ValueError) as exc:
            failed += 1
            print(f"failed: {src} -> {dest}: {exc}", file=sys.stderr)

    print("")
    print(f"done: moved={moved} failed={failed}")
    if moved > 0:
        _ = sync_tag_symlinks(target_root)
    return 0 if failed == 0 else 1


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


def cmd_fix(
    path: str,
    *,
    env_base_dir_key: str,
    archive_dir_name: str,
    is_under: Callable[[Path, Path], bool],
    suggest_project_root: Callable[[Path], Path],
    base_marker_file: str,
    prompt_yes_no: Callable[[str, bool], bool],
    parse_archive_timestamp: Callable[[str], int],
    ensure_base_marker: Callable[[Path], None],
    confirm: Callable[[], None],
) -> int:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        print(f"not found: {target}", file=sys.stderr)
        return 1
    if not target.is_dir():
        print(f"not a directory: {target}", file=sys.stderr)
        return 1

    base_dir = Path(os.environ.get(env_base_dir_key, ".")).resolve()
    archive_root = (base_dir / archive_dir_name).resolve()
    in_archive = is_under(target, archive_root)

    print(f"fix target: {target}")
    print(f"in archive: {'yes' if in_archive else 'no'}")

    marker_target = target
    if in_archive:
        marker_target = suggest_project_root(target)
        print(f"root candidate: {marker_target}")

    create_marker = False
    marker_file = marker_target / base_marker_file
    if marker_file.exists():
        print("base marker: exists")
    else:
        create_marker = prompt_yes_no(f"create {base_marker_file} in {marker_target}?", True)

    rename_src: Path | None = None
    rename_dest: Path | None = None
    if in_archive and "." in target.name:
        stem, suffix = target.name.rsplit(".", 1)
        ts = parse_archive_timestamp(suffix)
        if ts > 0:
            canonical = datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")
            fixed_name = f"{stem}.{canonical}"
            if fixed_name != target.name:
                candidate = target.with_name(fixed_name)
                if candidate.exists():
                    print(f"timestamp fix blocked (destination exists): {candidate}")
                else:
                    print(f"timestamp candidate: {target.name} -> {fixed_name}")
                    if prompt_yes_no("apply timestamp rename?", True):
                        rename_src = target
                        rename_dest = candidate
        else:
            print("timestamp fix: could not parse suffix")

    print("\nsummary:")
    print(f"  - create marker: {'yes' if create_marker else 'no'}")
    if rename_src and rename_dest:
        print(f"  - rename archive dir: {rename_src.name} -> {rename_dest.name}")
    else:
        print("  - rename archive dir: no")

    if not create_marker and not (rename_src and rename_dest):
        print("nothing to do")
        return 0

    confirm()
    if create_marker:
        ensure_base_marker(marker_target)
        print(f"created: {marker_target / base_marker_file}")
    if rename_src and rename_dest:
        rename_src.rename(rename_dest)
        print(f"renamed: {rename_src} -> {rename_dest}")
    print("done")
    return 0
