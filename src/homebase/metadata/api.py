from __future__ import annotations

import os
import shlex
from pathlib import Path

import yaml
from rich.text import Text

from ..archive import io as archive_io
from ..config.property_defs import load_property_defs
from ..core import utils as core_utils
from ..core.constants import (
    ARCHIVE_TZ,
    BASE_MARKER_FILE,
    BASE_META_ALLOWED_KEYS,
    COLOR_AGE_UNIT_HEX,
    DYNAMIC_PROPERTY_DEFS,
    ENV_BASE_DIR,
    GLOBAL_CONFIG_FILE_NAME,
    HOMEBASE_DIR_NAME,
    LEGACY_BASE_MARKER_FILE,
    LEVEL_ERROR,
    PACKED_ARCHIVE_SUFFIX,
    PROPERTY_DEFS,
)
from ..core.models import ProjectRow, PropertyDef
from ..filter import tag_index
from ..workspace import project_info
from . import property as property_utils
from . import store as metadata_store
from . import utils as metadata_utils

_RUNTIME_PROPERTY_DEFS_BASE: Path | None = None
_RUNTIME_PROPERTY_DEFS_MTIME_NS: int = -1
_RUNTIME_PROPERTY_DEFS_CACHE: list[PropertyDef] = []


def _is_packed_archive_path(path: Path) -> bool:
    return core_utils.is_packed_archive_path(path, PACKED_ARCHIVE_SUFFIX)


def _packed_read_base_data(path: Path) -> dict[str, object]:
    return archive_io.packed_read_base_data(path, base_marker_file=BASE_MARKER_FILE)


def _packed_write_base_data(path: Path, data: dict[str, object]) -> None:
    archive_io.packed_write_base_data(path, data, base_marker_file=BASE_MARKER_FILE)


def _archive_now_iso() -> str:
    return core_utils.archive_now_iso(ARCHIVE_TZ)


def load_base_meta(path: Path) -> tuple[list[str], str, bool]:
    return metadata_utils.extract_base_meta_fields(load_base_data(path))


def base_meta_issues(path: Path) -> list[tuple[str, str, str]]:
    if _is_packed_archive_path(path):
        raw = load_base_data(path)
        if not raw:
            return [
                (
                    LEVEL_ERROR,
                    "pkg_missing_meta",
                    f"packed archive is missing {BASE_MARKER_FILE} metadata",
                )
            ]
        if not isinstance(raw, dict):
            return [("warning", "invalid_root", "root must be a mapping")]
    else:
        meta_file = path / BASE_MARKER_FILE
        legacy_meta_file = path / LEGACY_BASE_MARKER_FILE
        if legacy_meta_file.is_file() and meta_file.is_file():
            return [
                (
                    LEVEL_ERROR,
                    "legacy_conflict",
                    f"both {BASE_MARKER_FILE} and {LEGACY_BASE_MARKER_FILE} exist (merge content and remove {LEGACY_BASE_MARKER_FILE})",
                )
            ]
        if not meta_file.is_file():
            if legacy_meta_file.is_file():
                return [
                    (
                        LEVEL_ERROR,
                        "legacy_only",
                        f"uses {LEGACY_BASE_MARKER_FILE} without {BASE_MARKER_FILE} (merge/migrate to {BASE_MARKER_FILE})",
                    )
                ]
            return [("warning", "missing_meta", f"missing {BASE_MARKER_FILE}")]
        try:
            raw = yaml.safe_load(meta_file.read_text())
        except (OSError, yaml.YAMLError) as exc:
            return [("warning", "invalid_yaml", f"invalid yaml: {exc}")]
    return metadata_utils.base_meta_schema_issues(
        raw,
        allowed_keys=BASE_META_ALLOWED_KEYS,
    )


def base_meta_health(path: Path) -> tuple[str, str]:
    issues = base_meta_issues(path)
    if not issues:
        return "ok", ""
    if any(level == LEVEL_ERROR for level, _code, _msg in issues):
        msg = "; ".join(msg for level, _code, msg in issues if level == LEVEL_ERROR)
        return LEVEL_ERROR, msg
    msg = "; ".join(msg for _level, _code, msg in issues)
    return "warning", msg


def load_base_data(path: Path) -> dict[str, object]:
    return metadata_store.load_base_data(
        path,
        is_packed_archive_path=_is_packed_archive_path,
        packed_read_base_data=_packed_read_base_data,
        base_marker_file=BASE_MARKER_FILE,
    )


def save_base_data(path: Path, data: dict[str, object]) -> None:
    metadata_store.save_base_data(
        path,
        data,
        is_packed_archive_path=_is_packed_archive_path,
        packed_write_base_data=_packed_write_base_data,
        base_marker_file=BASE_MARKER_FILE,
    )


def ensure_base_marker(path: Path) -> None:
    metadata_store.ensure_base_marker(
        path,
        is_packed_archive_path=_is_packed_archive_path,
        base_marker_file=BASE_MARKER_FILE,
    )


def normalize_base_data(data: dict[str, object]) -> tuple[dict[str, object], list[str]]:
    return metadata_utils.normalize_base_data(data)


def repair_base_metadata(path: Path) -> tuple[bool, str]:
    return metadata_store.repair_base_metadata(
        path,
        base_marker_file=BASE_MARKER_FILE,
        normalize_base_data_fn=normalize_base_data,
        save_base_data_fn=save_base_data,
        append_base_log_fn=append_base_log,
    )


def normalize_base_metadata(path: Path) -> tuple[bool, str]:
    return metadata_store.normalize_base_metadata(
        path,
        base_marker_file=BASE_MARKER_FILE,
        normalize_base_data_fn=normalize_base_data,
        save_base_data_fn=save_base_data,
        append_base_log_fn=append_base_log,
    )


def rename_legacy_base_yaml(path: Path) -> tuple[bool, str]:
    return metadata_store.rename_legacy_base_yaml(
        path,
        legacy_base_marker_file=LEGACY_BASE_MARKER_FILE,
        base_marker_file=BASE_MARKER_FILE,
        append_base_log_fn=append_base_log,
    )


def open_meta_for_review(path: Path) -> tuple[bool, str]:
    return metadata_store.open_meta_for_review(
        path,
        base_marker_file=BASE_MARKER_FILE,
        legacy_base_marker_file=LEGACY_BASE_MARKER_FILE,
    )


def append_base_log(
    path: Path, event: str, payload: dict[str, object] | None = None
) -> None:
    metadata_store.append_base_log(
        path,
        event,
        payload,
        ensure_base_marker_fn=ensure_base_marker,
        load_base_data_fn=load_base_data,
        save_base_data_fn=save_base_data,
        now_iso=_archive_now_iso,
    )


def detect_properties(path: Path, *, archived: bool = False) -> list[str]:
    runtime_property_defs = _runtime_property_defs()
    template_context = _property_template_context(path, archived=archived)
    return property_utils.detect_properties(
        path,
        property_defs=runtime_property_defs,
        normalize_keys=normalize_property_keys,
        template_context=template_context,
    )


def all_property_defs() -> list[PropertyDef]:
    return [
        p
        for p in property_utils.all_property_defs(
            DYNAMIC_PROPERTY_DEFS,
            _runtime_property_defs(),
        )
        if isinstance(p, PropertyDef)
    ]


def normalize_property_keys(keys: list[str]) -> list[str]:
    return property_utils.normalize_property_keys(
        keys,
        dynamic_property_defs=DYNAMIC_PROPERTY_DEFS,
        property_defs=_runtime_property_defs(),
    )


def _runtime_property_defs() -> list[PropertyDef]:
    global _RUNTIME_PROPERTY_DEFS_BASE, _RUNTIME_PROPERTY_DEFS_MTIME_NS, _RUNTIME_PROPERTY_DEFS_CACHE
    base = os.environ.get(ENV_BASE_DIR, "").strip()
    if not base:
        return list(PROPERTY_DEFS)
    base_path = Path(base)
    base_res = base_path.resolve()
    conf = base_path / HOMEBASE_DIR_NAME / GLOBAL_CONFIG_FILE_NAME
    try:
        mtime_ns = int(conf.stat().st_mtime_ns) if conf.is_file() else -1
    except OSError:
        mtime_ns = -1
    if _RUNTIME_PROPERTY_DEFS_BASE == base_res and _RUNTIME_PROPERTY_DEFS_MTIME_NS == mtime_ns:
        return list(_RUNTIME_PROPERTY_DEFS_CACHE)
    loaded = load_property_defs(base_path)
    _RUNTIME_PROPERTY_DEFS_BASE = base_res
    _RUNTIME_PROPERTY_DEFS_MTIME_NS = mtime_ns
    _RUNTIME_PROPERTY_DEFS_CACHE = list(loaded)
    return list(loaded)


def _property_template_context(path: Path, *, archived: bool) -> dict[str, str]:
    base_dir = os.environ.get(ENV_BASE_DIR, "").strip()
    base_path = Path(base_dir).expanduser().resolve() if base_dir else path.parent
    rel_path = path
    try:
        rel_path = path.relative_to(base_path)
    except ValueError:
        pass
    archive_prefix = "_archive/" if archived else ""
    archive_prefixed_name = f"{archive_prefix}{path.name}"
    out = {
        "NAME": path.name,
        "PROJECT_NAME": path.name,
        "NAME_WITH_ARCHIVE_PREFIX": archive_prefixed_name,
        "ARCHIVE_PREFIX": archive_prefix,
        "PROJECT_PATH": str(path),
        "FULL_PATH": str(path),
        "REL_PATH": str(rel_path),
        "BASE_DIR": str(base_path),
    }
    for key, value in list(out.items()):
        out[key.lower()] = value
    out["NAME_WITH_ARCHIVE_PREFIX_Q"] = shlex.quote(archive_prefixed_name)
    out["name_with_archive_prefix_q"] = out["NAME_WITH_ARCHIVE_PREFIX_Q"]
    return out


def property_tokens(keys: list[str]) -> str:
    return property_utils.property_tokens(
        keys,
        all_defs=all_property_defs(),
        normalize_keys=normalize_property_keys,
    )


def property_tokens_text(keys: list[str]) -> Text:
    return property_utils.property_tokens_text(
        keys,
        all_defs=all_property_defs(),
        normalize_keys=normalize_property_keys,
    )


def property_display_lines(keys: list[str]) -> list[str]:
    return property_utils.property_display_lines(
        keys,
        all_defs=all_property_defs(),
        normalize_keys=normalize_property_keys,
    )


def build_project_info_text(
    base_dir: Path,
    row: ProjectRow,
    wip_hotkey: int | None = None,
    include_meta_checks: bool = True,
) -> str:
    return project_info.build_project_info_text(
        row,
        base_marker_file=BASE_MARKER_FILE,
        legacy_base_marker_file=LEGACY_BASE_MARKER_FILE,
        color_age_unit_hex=COLOR_AGE_UNIT_HEX,
        wip_hotkey=wip_hotkey,
        include_meta_checks=include_meta_checks,
        fmt_iso=core_utils.fmt_iso,
        fmt_age_short=core_utils.fmt_age_short,
        property_display_lines=property_display_lines,
        base_meta_issues=base_meta_issues,
        load_base_data=load_base_data,
        run_out=core_utils.run_out,
    )


def _safe_tag_component(tag: str) -> str:
    return tag_index.safe_tag_component(tag)


def _safe_link_name(name: str) -> str:
    return tag_index.safe_link_name(name)


def _project_tag_link_name(base_dir: Path, project_path: Path) -> str:
    return tag_index.project_tag_link_name(base_dir, project_path)


def sync_tag_symlinks_detailed(
    base_dir: Path, verbose: bool = False, debug: bool = False
) -> tuple[str | None, list[str]]:
    from . import app_workspace

    return tag_index.sync_tag_symlinks_detailed(
        base_dir,
        base_marker_file=BASE_MARKER_FILE,
        collect_projects=app_workspace.collect_projects,
        verbose=verbose,
        debug=debug,
    )


def sync_tag_symlinks(base_dir: Path) -> str | None:
    from . import app_workspace

    return tag_index.sync_tag_symlinks(
        base_dir,
        base_marker_file=BASE_MARKER_FILE,
        collect_projects=app_workspace.collect_projects,
    )


def save_base_tags(_base_dir: Path, path: Path, new_tags: list[str]) -> None:
    ensure_base_marker(path)
    data = load_base_data(path)
    tags = sorted({t.strip() for t in new_tags if t.strip()})
    if tags:
        data["tags"] = tags
    else:
        data.pop("tags", None)
    save_base_data(path, data)


def save_base_description(path: Path, description: str) -> None:
    ensure_base_marker(path)
    data = load_base_data(path)
    desc = description.strip()
    if desc:
        data["description"] = desc
    else:
        data.pop("description", None)
    save_base_data(path, data)


def save_base_wip(path: Path, wip: bool) -> None:
    ensure_base_marker(path)
    data = load_base_data(path)
    if wip:
        data["wip"] = True
    else:
        data.pop("wip", None)
    save_base_data(path, data)
