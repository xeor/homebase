from __future__ import annotations

import os
import shlex
from pathlib import Path

import yaml
from rich.text import Text

from ..config.property_defs import load_property_defs
from ..core import packed_meta
from ..core import utils as core_utils
from ..core.constants import (
    ARCHIVE_TZ,
    BASE_MARKER_FILE,
    BASE_META_ALLOWED_KEYS,
    DYNAMIC_PROPERTY_DEFS,
    ENV_BASE_DIR,
    GLOBAL_CONFIG_FILE_NAME,
    HOMEBASE_DIR_NAME,
    LEGACY_BASE_MARKER_FILE,
    LEVEL_ERROR,
    PACKED_ARCHIVE_SUFFIX,
    PROPERTY_DEFS,
)
from ..core.models import PropertyDef
from . import property as property_utils
from . import store as metadata_store
from . import utils as metadata_utils

_RUNTIME_PROPERTY_DEFS_BASE: Path | None = None
_RUNTIME_PROPERTY_DEFS_MTIME_NS: int = -1
_RUNTIME_PROPERTY_DEFS_CACHE: list[PropertyDef] = []


def _is_packed_archive_path(path: Path) -> bool:
    return core_utils.is_packed_archive_path(path, PACKED_ARCHIVE_SUFFIX)


def _packed_read_base_data(path: Path) -> dict[str, object]:
    return packed_meta.packed_read_base_data(path, base_marker_file=BASE_MARKER_FILE)


def _packed_write_base_data(path: Path, data: dict[str, object]) -> None:
    packed_meta.packed_write_base_data(path, data, base_marker_file=BASE_MARKER_FILE)


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


def property_defs_signature() -> int:
    _runtime_property_defs()
    return _RUNTIME_PROPERTY_DEFS_MTIME_NS


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
    archive_prefix = ""
    if archived:
        year_part = ""
        try:
            rel_parts = path.relative_to(base_path).parts
        except ValueError:
            rel_parts = path.parts
        if (
            len(rel_parts) >= 3
            and rel_parts[0] == "_archive"
            and len(rel_parts[1]) == 4
            and rel_parts[1].isdigit()
        ):
            year_part = f"{rel_parts[1]}/"
        archive_prefix = f"_archive/{year_part}"
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


_PROPERTY_TOKENS_CACHE: dict[tuple[tuple[str, ...], int], str] = {}
_PROPERTY_TOKENS_CACHE_MAX = 4096


def property_tokens(keys: list[str]) -> str:
    cache_key = (tuple(keys), property_defs_signature())
    cached = _PROPERTY_TOKENS_CACHE.get(cache_key)
    if cached is not None:
        return cached
    if len(_PROPERTY_TOKENS_CACHE) >= _PROPERTY_TOKENS_CACHE_MAX:
        _PROPERTY_TOKENS_CACHE.clear()
    result = property_utils.property_tokens(
        keys,
        all_defs=all_property_defs(),
        normalize_keys=normalize_property_keys,
    )
    _PROPERTY_TOKENS_CACHE[cache_key] = result
    return result


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


def save_base_worktree(
    path: Path,
    *,
    of: str,
    branch: str,
    parent_path: str | None = None,
    gitdir_id: str | None = None,
) -> None:
    of_value = of.strip()
    branch_value = branch.strip()
    if not of_value or not branch_value:
        raise ValueError("worktree.of and worktree.branch must be non-empty")
    block: dict[str, object] = {"of": of_value, "branch": branch_value}
    if parent_path is not None:
        parent_value = parent_path.strip()
        if not parent_value:
            raise ValueError("worktree.parent_path must be non-empty when provided")
        if not Path(parent_value).is_absolute():
            raise ValueError("worktree.parent_path must be absolute")
        block["parent_path"] = parent_value
    if gitdir_id is not None:
        gitdir_value = gitdir_id.strip()
        if not gitdir_value:
            raise ValueError("worktree.gitdir_id must be non-empty when provided")
        block["gitdir_id"] = gitdir_value
    ensure_base_marker(path)
    data = load_base_data(path)
    data["worktree"] = block
    save_base_data(path, data)


def load_base_worktree(path: Path) -> dict[str, str] | None:
    data = load_base_data(path)
    raw = data.get("worktree")
    if not isinstance(raw, dict):
        return None
    out: dict[str, str] = {}
    for key in ("of", "branch", "parent_path", "gitdir_id"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value
    if "of" not in out or "branch" not in out:
        return None
    return out


def clear_base_worktree(path: Path) -> None:
    ensure_base_marker(path)
    data = load_base_data(path)
    if data.pop("worktree", None) is None:
        return
    save_base_data(path, data)


def load_base_repo_dir(path: Path) -> str:
    """Return the project's configured repo subpath (relative). Empty
    string means 'not configured' — callers should treat the project
    as having no git repo to show."""
    data = load_base_data(path)
    raw = data.get("repo_dir")
    if not isinstance(raw, str):
        return ""
    value = raw.strip()
    if not value:
        return ""
    if Path(value).is_absolute():
        return ""
    return value


def resolve_project_repo(path: Path) -> Path | None:
    """Absolute path to the project's main git repo, or None when
    repo_dir is unset / invalid. Existence is the caller's check."""
    repo_dir = load_base_repo_dir(path)
    if not repo_dir:
        return None
    return path / repo_dir


def save_base_repo_dir(path: Path, repo_dir: str) -> None:
    value = repo_dir.strip()
    if not value:
        raise ValueError("repo_dir must be non-empty")
    if Path(value).is_absolute():
        raise ValueError("repo_dir must be relative")
    ensure_base_marker(path)
    data = load_base_data(path)
    data["repo_dir"] = value
    save_base_data(path, data)


def clear_base_repo_dir(path: Path) -> None:
    ensure_base_marker(path)
    data = load_base_data(path)
    if data.pop("repo_dir", None) is None:
        return
    save_base_data(path, data)
