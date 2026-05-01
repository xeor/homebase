from __future__ import annotations

import subprocess
import time
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Callable

# Defensive catch for textual widget property writes that can fail
# transiently during teardown / re-mount.
WIDGET_API_ERRORS = (AttributeError, RuntimeError, ValueError, TypeError)


def run_out(*cmd: str, check: bool = True) -> str:
    p = subprocess.run(cmd, check=check, text=True, capture_output=True)
    return p.stdout.strip()


def resolve_base_dir(base_folder_arg: str | None, env_base_folder: str | None) -> Path:
    if base_folder_arg and str(base_folder_arg).strip():
        return Path(str(base_folder_arg).strip()).expanduser().resolve()
    env_base = (env_base_folder or "").strip()
    if env_base:
        return Path(env_base).expanduser().resolve()
    return (Path.home() / "base").resolve()


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def restore_symlink_boundary(base_dir: Path, target_abs: Path) -> Path | None:
    base_res = base_dir.resolve()
    try:
        rel = target_abs.relative_to(base_res)
    except ValueError:
        return None
    cur = base_res
    for part in rel.parts:
        cur = cur / part
        if cur.exists() and cur.is_symlink():
            return cur
    return None


def normalize_restore_target(
    base_dir: Path,
    target: Path,
    *,
    allow_outside_base: bool = False,
) -> Path:
    base_res = base_dir.resolve()
    target_abs = target if target.is_absolute() else (base_res / target)
    target_res = target_abs.resolve()
    if target_res == base_res:
        raise ValueError(f"restore target cannot be base directory: {target_res}")
    if not allow_outside_base and not is_under(target_res, base_res):
        raise ValueError(f"restore target outside base is not allowed: {target_res}")
    if not allow_outside_base:
        boundary = restore_symlink_boundary(base_res, target_abs)
        if boundary is not None:
            raise ValueError(f"restore target crosses symlink boundary: {boundary}")
    return target_res


def fmt_ymd(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def fmt_iso(ts: int) -> str:
    return datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def fmt_age_short(ts: int, now_ts: int | None = None) -> str:
    if ts <= 0:
        return "-0m"
    now = int(now_ts if now_ts is not None else time.time())
    delta = max(0, now - ts)
    total_minutes = delta // 60
    total_days = total_minutes // (24 * 60)
    years = total_days // 365
    days = total_days % 365
    rem = total_minutes % (24 * 60)
    hours = rem // 60
    minutes = rem % 60
    parts: list[str] = []
    if years > 0:
        parts.append(f"{years}y")
    if days > 0:
        parts.append(f"{days}d")
    if years > 0 or days > 0 or hours > 0:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return "-" + "".join(parts)


def fmt_size_human(n: int) -> str:
    value = float(max(0, int(n)))
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while value >= 1024.0 and idx < len(units) - 1:
        value /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(value)} {units[idx]}"
    return f"{value:.1f} {units[idx]}"


def fmt_age_short_from_iso(iso_text: str, now_ts: int | None = None) -> str:
    try:
        dt = datetime.fromisoformat(iso_text)
        return fmt_age_short(int(dt.timestamp()), now_ts)
    except ValueError:
        return "-0m"


def archive_now_iso(archive_tz: tzinfo) -> str:
    return datetime.now(archive_tz).isoformat(timespec="seconds")


def archive_iso_from_ts(ts: int, archive_tz: tzinfo) -> str:
    return datetime.fromtimestamp(ts, archive_tz).isoformat(timespec="seconds")


def parse_archive_timestamp(value: str, archive_tz: tzinfo) -> int:
    s = value.strip()
    if not s:
        return 0
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=archive_tz)
        return int(dt.timestamp())
    except ValueError:
        pass
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d_%H:%M:%S",
        "%Y%m%dT%H%M%S",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=archive_tz)
            return int(dt.timestamp())
        except ValueError:
            continue
    return 0


def split_archive_name(name: str, parse_timestamp: Callable[[str], int]) -> tuple[str, int]:
    if "." not in name:
        return name, 0
    stem, suffix = name.rsplit(".", 1)
    ts = parse_timestamp(suffix)
    if ts <= 0:
        return name, 0
    return stem, ts


def is_packed_archive_path(path: Path, packed_archive_suffix: str) -> bool:
    return path.is_file() and path.name.endswith(packed_archive_suffix)


def packed_archive_dir_name(path: Path, packed_archive_suffix: str) -> str:
    name = path.name
    if name.endswith(packed_archive_suffix):
        return name[: -len(packed_archive_suffix)]
    return name


def split_archive_entry_name(
    path: Path,
    *,
    packed_archive_suffix: str,
    parse_timestamp: Callable[[str], int],
) -> tuple[str, int]:
    raw = (
        packed_archive_dir_name(path, packed_archive_suffix)
        if path.name.endswith(packed_archive_suffix)
        else path.name
    )
    return split_archive_name(raw, parse_timestamp=parse_timestamp)
