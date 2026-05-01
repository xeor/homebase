from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml


def load_base_data(
    path: Path,
    *,
    is_packed_archive_path: Callable[[Path], bool],
    packed_read_base_data: Callable[[Path], dict[str, object]],
    base_marker_file: str,
) -> dict[str, object]:
    if is_packed_archive_path(path):
        return packed_read_base_data(path)
    meta_file = path / base_marker_file
    if not meta_file.is_file():
        return {}
    try:
        raw = yaml.safe_load(meta_file.read_text())
    except (OSError, yaml.YAMLError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_base_data(
    path: Path,
    data: dict[str, object],
    *,
    is_packed_archive_path: Callable[[Path], bool],
    packed_write_base_data: Callable[[Path, dict[str, object]], None],
    base_marker_file: str,
) -> None:
    if is_packed_archive_path(path):
        packed_write_base_data(path, data)
        return
    meta_file = path / base_marker_file
    if data:
        meta_file.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
    else:
        meta_file.write_text("\n")


def ensure_base_marker(
    path: Path,
    *,
    is_packed_archive_path: Callable[[Path], bool],
    base_marker_file: str,
) -> None:
    if is_packed_archive_path(path):
        return
    marker = path / base_marker_file
    if marker.exists():
        return
    marker.write_text("\n")


def append_base_log(
    path: Path,
    event: str,
    payload: dict[str, object] | None = None,
    *,
    ensure_base_marker_fn: Callable[[Path], None],
    load_base_data_fn: Callable[[Path], dict[str, object]],
    save_base_data_fn: Callable[[Path, dict[str, object]], None],
    now_iso: Callable[[], str],
) -> None:
    ensure_base_marker_fn(path)
    data = load_base_data_fn(path)
    log_val = data.get("log", {})
    if not isinstance(log_val, dict):
        log_val = {}
    events = log_val.get("events", [])
    if not isinstance(events, list):
        events = []

    entry: dict[str, object] = {"_event": event, "_ts": now_iso()}
    if payload:
        for key, value in payload.items():
            if key in {"_event", "_ts"}:
                continue
            entry[key] = value
    events.append(entry)
    log_val["events"] = events[-500:]
    data["log"] = log_val
    save_base_data_fn(path, data)


def save_base_opened(
    path: Path,
    opened_ts: int | None,
    *,
    ensure_base_marker_fn: Callable[[Path], None],
    load_base_data_fn: Callable[[Path], dict[str, object]],
    save_base_data_fn: Callable[[Path, dict[str, object]], None],
) -> int:
    ensure_base_marker_fn(path)
    ts = int(opened_ts if opened_ts is not None else time.time())
    if ts < 0:
        ts = int(time.time())
    data = load_base_data_fn(path)
    data["opened_ts"] = ts
    data["opened_at"] = datetime.fromtimestamp(ts).isoformat(timespec="seconds")
    save_base_data_fn(path, data)
    return ts


def repair_base_metadata(
    path: Path,
    *,
    base_marker_file: str,
    normalize_base_data_fn: Callable[[dict[str, object]], tuple[dict[str, object], list[str]]],
    save_base_data_fn: Callable[[Path, dict[str, object]], None],
    append_base_log_fn: Callable[[Path, str, dict[str, object] | None], None],
) -> tuple[bool, str]:
    meta_file = path / base_marker_file
    raw: dict[str, object] = {}
    if meta_file.is_file():
        try:
            loaded = yaml.safe_load(meta_file.read_text())
            if isinstance(loaded, dict):
                raw = loaded
        except (OSError, yaml.YAMLError):
            raw = {}

    normalized, notes = normalize_base_data_fn(raw)
    save_base_data_fn(path, normalized)
    append_base_log_fn(path, "meta_repaired", {"notes": ", ".join(notes) if notes else "ok"})
    return True, "metadata repaired"


def normalize_base_metadata(
    path: Path,
    *,
    base_marker_file: str,
    normalize_base_data_fn: Callable[[dict[str, object]], tuple[dict[str, object], list[str]]],
    save_base_data_fn: Callable[[Path, dict[str, object]], None],
    append_base_log_fn: Callable[[Path, str, dict[str, object] | None], None],
) -> tuple[bool, str]:
    meta_file = path / base_marker_file
    if not meta_file.is_file():
        return False, f"missing {base_marker_file}"
    try:
        raw = yaml.safe_load(meta_file.read_text())
    except (OSError, yaml.YAMLError) as exc:
        return False, f"invalid yaml: {exc}"
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return False, "root must be a mapping"
    normalized, notes = normalize_base_data_fn(raw)
    save_base_data_fn(path, normalized)
    append_base_log_fn(path, "meta_normalized", {"notes": ", ".join(notes) if notes else "ok"})
    return True, "metadata normalized"


def rename_legacy_base_yaml(
    path: Path,
    *,
    legacy_base_marker_file: str,
    base_marker_file: str,
    append_base_log_fn: Callable[[Path, str, dict[str, object] | None], None],
) -> tuple[bool, str]:
    src = path / legacy_base_marker_file
    dst = path / base_marker_file
    if not src.is_file():
        return False, f"missing {legacy_base_marker_file}"
    if dst.exists():
        return False, f"{base_marker_file} already exists"
    src.rename(dst)
    append_base_log_fn(
        path,
        "meta_renamed_ext",
        {"from": legacy_base_marker_file, "to": base_marker_file},
    )
    return True, f"renamed {legacy_base_marker_file} -> {base_marker_file}"


def open_meta_for_review(
    path: Path,
    *,
    base_marker_file: str,
    legacy_base_marker_file: str,
) -> tuple[bool, str]:
    target = path / base_marker_file
    if not target.exists():
        legacy = path / legacy_base_marker_file
        if legacy.exists():
            target = legacy
    if not target.exists():
        return False, "metadata file not found"
    try:
        if shutil.which("open") is not None:
            subprocess.Popen(["open", str(target)])
            return True, f"opened: {target.name}"
    except (OSError, subprocess.SubprocessError):
        pass
    return False, f"open manually: {target}"
