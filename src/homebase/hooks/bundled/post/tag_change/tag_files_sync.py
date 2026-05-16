from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from homebase.metadata.api import load_base_data

from ....api import HookContext

DESCRIPTION = (
    "On tag add, symlink files from <root>/<tag>/ into the project "
    "(never overwrites). On tag remove, unlink only the symlinks that still "
    "point to the same source. Edits to source files propagate automatically "
    "through the symlinks. <root> defaults to <base>/.homebase/tag-files/ "
    "and can be overridden via config.root (relative to base_dir or absolute, "
    "with ~ expansion)."
)

HOMEBASE_DIR_NAME = ".homebase"
TAG_FILES_DIR_NAME = "tag-files"
DEFAULT_ROOT_REL = f"{HOMEBASE_DIR_NAME}/{TAG_FILES_DIR_NAME}"

_REPORT_LIMIT = 5


def run(ctx: HookContext) -> None:
    base_dir = ctx.base_dir
    dry_run = bool(ctx.hook.config.get("dry_run", False))
    config_root = ctx.hook.config.get("root")
    root_dir = _resolve_root_dir(base_dir, config_root)

    if not root_dir.is_dir() or root_dir.is_symlink():
        if _root_is_explicit(config_root):
            ctx.notify(
                f"tag-files: root not a usable directory: {root_dir}",
                "warn",
            )
        return

    per_target_raw = ctx.change.get("per_target")
    per_target = per_target_raw if isinstance(per_target_raw, dict) else {}

    for target in ctx.targets:
        info = per_target.get(target.path) or per_target.get(str(target.path)) or {}
        added = [str(t) for t in info.get("added", []) if str(t).strip()]
        removed = [str(t) for t in info.get("removed", []) if str(t).strip()]

        for tag in added:
            src_root = _resolve_tag_root(root_dir, tag)
            if src_root is None:
                continue
            _link_tag_files(ctx, target.path, tag, src_root, dry_run=dry_run)

        for tag in removed:
            src_root = _resolve_tag_root(root_dir, tag)
            _unlink_tag_files(
                ctx,
                target.path,
                tag,
                root_dir,
                src_root,
                dry_run=dry_run,
            )


def _root_is_explicit(config_root: object) -> bool:
    return config_root is not None and str(config_root).strip() != ""


def _resolve_root_dir(base_dir: Path, config_root: object) -> Path:
    if not _root_is_explicit(config_root):
        return base_dir / HOMEBASE_DIR_NAME / TAG_FILES_DIR_NAME
    raw = os.path.expanduser(str(config_root).strip())
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate


def _resolve_tag_root(root_dir: Path, tag: str) -> Path | None:
    parent = root_dir.resolve()
    candidate = (root_dir / tag).resolve()
    try:
        candidate.relative_to(parent)
    except ValueError:
        return None
    if candidate == parent:
        return None
    if not candidate.is_dir() or candidate.is_symlink():
        return None
    return candidate


def _iter_entries(src_root: Path) -> Iterator[tuple[Path, str]]:
    src_root_resolved = src_root.resolve()
    for dirpath, dirnames, filenames in os.walk(src_root, followlinks=False):
        here = Path(dirpath)
        try:
            here_resolved = here.resolve()
            here_resolved.relative_to(src_root_resolved)
        except (ValueError, OSError):
            dirnames[:] = []
            continue
        kept_dirs: list[str] = []
        for name in dirnames:
            entry = here / name
            if entry.is_symlink():
                continue
            kept_dirs.append(name)
            yield entry.relative_to(src_root), "dir"
        dirnames[:] = kept_dirs
        for name in filenames:
            entry = here / name
            if entry.is_symlink() or not entry.is_file():
                continue
            yield entry.relative_to(src_root), "file"


def _safe_dest(project: Path, rel: Path) -> Path | None:
    if not rel.parts or rel.is_absolute():
        return None
    if any(part in ("", ".", "..") for part in rel.parts):
        return None
    return project / rel


def _expected_target(src_root: Path, rel: Path) -> str:
    return str((src_root / rel).resolve())


def _symlink_target(path: Path) -> str | None:
    try:
        return os.readlink(path)
    except OSError:
        return None


def _format_summary(items: list[str]) -> str:
    if len(items) <= _REPORT_LIMIT:
        return ", ".join(items)
    return ", ".join(items[:_REPORT_LIMIT]) + f", +{len(items) - _REPORT_LIMIT} more"


def _link_tag_files(
    ctx: HookContext,
    project: Path,
    tag: str,
    src_root: Path,
    *,
    dry_run: bool,
) -> None:
    if not project.is_dir() or project.is_symlink():
        ctx.notify(f"tag-files [{tag}]: project missing, skipped", "warn")
        return

    linked: list[str] = []
    skipped_existing_file: list[str] = []
    skipped_other_symlink: list[str] = []
    skipped_conflict: list[str] = []
    skipped_unsafe: list[str] = []

    for rel, kind in _iter_entries(src_root):
        dest = _safe_dest(project, rel)
        if dest is None:
            skipped_unsafe.append(str(rel))
            continue

        if kind == "dir":
            if dest.is_symlink() or (dest.exists() and not dest.is_dir()):
                skipped_conflict.append(str(rel))
                continue
            if dest.exists():
                continue
            if not dry_run:
                try:
                    dest.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    ctx.notify(f"tag-files [{tag}]: mkdir failed for {rel}: {exc}", "warn")
            continue

        expected = _expected_target(src_root, rel)
        if dest.is_symlink():
            if _symlink_target(dest) == expected:
                continue
            skipped_other_symlink.append(str(rel))
            continue
        if dest.exists():
            skipped_existing_file.append(str(rel))
            continue

        if dry_run:
            linked.append(str(rel))
            continue

        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(expected, dest)
            linked.append(str(rel))
            ctx.add_event(
                project,
                "tag_files_linked",
                {"tag": tag, "rel": str(rel), "target": expected},
            )
        except OSError as exc:
            ctx.notify(f"tag-files [{tag}]: symlink failed for {rel}: {exc}", "warn")

    if skipped_existing_file:
        ctx.notify(
            f"tag-files [{tag}]: real file in the way, kept user's: "
            f"{_format_summary(skipped_existing_file)}",
            "warn",
        )
    if skipped_other_symlink:
        ctx.notify(
            f"tag-files [{tag}]: existing symlink points elsewhere, kept: "
            f"{_format_summary(skipped_other_symlink)}",
            "warn",
        )
    if skipped_conflict:
        ctx.notify(
            f"tag-files [{tag}]: type conflict, skipped: "
            f"{_format_summary(skipped_conflict)}",
            "warn",
        )
    if skipped_unsafe:
        ctx.notify(
            f"tag-files [{tag}]: unsafe path, skipped: "
            f"{_format_summary(skipped_unsafe)}",
            "error",
        )
    if linked:
        prefix = "would link" if dry_run else "linked"
        ctx.status_update(f"tag-files [{tag}]: {prefix} {len(linked)} file(s)", "info")


def _unlink_tag_files(
    ctx: HookContext,
    project: Path,
    tag: str,
    root_dir: Path,
    src_root: Path | None,
    *,
    dry_run: bool,
) -> None:
    if not project.is_dir() or project.is_symlink():
        return

    candidates: dict[str, str] = {}
    dirs_from_source: list[Path] = []
    if src_root is not None:
        for rel, kind in _iter_entries(src_root):
            if kind == "file":
                candidates[str(rel)] = _expected_target(src_root, rel)
            elif kind == "dir":
                dirs_from_source.append(rel)

    known = _last_known_links(project, root_dir)
    for rel_str, info in known.items():
        if info.get("tag") != tag:
            continue
        candidates.setdefault(rel_str, info["target"])

    removed: list[str] = []
    skipped_not_link: list[str] = []
    skipped_other_target: list[str] = []
    skipped_unsafe: list[str] = []

    for rel_str, expected in sorted(candidates.items()):
        rel = Path(rel_str)
        dest = _safe_dest(project, rel)
        if dest is None:
            skipped_unsafe.append(rel_str)
            continue
        if not dest.is_symlink():
            if dest.exists():
                skipped_not_link.append(rel_str)
            continue
        if _symlink_target(dest) != expected:
            skipped_other_target.append(rel_str)
            continue
        if dry_run:
            removed.append(rel_str)
            continue
        try:
            dest.unlink()
            removed.append(rel_str)
            ctx.add_event(
                project,
                "tag_files_unlinked",
                {"tag": tag, "rel": rel_str, "target": expected},
            )
        except OSError as exc:
            ctx.notify(f"tag-files [{tag}]: unlink failed for {rel_str}: {exc}", "warn")

    for rel in sorted(dirs_from_source, key=lambda p: len(p.parts), reverse=True):
        dest = _safe_dest(project, rel)
        if dest is None:
            continue
        if not dest.is_dir() or dest.is_symlink():
            continue
        try:
            next(dest.iterdir())
            continue
        except StopIteration:
            pass
        except OSError:
            continue
        if dry_run:
            continue
        try:
            dest.rmdir()
        except OSError:
            pass

    if not dry_run and removed:
        _prune_empty_dirs(project, removed)

    if skipped_not_link:
        ctx.notify(
            f"tag-files [{tag}]: replaced by real file, kept: "
            f"{_format_summary(skipped_not_link)}",
            "warn",
        )
    if skipped_other_target:
        ctx.notify(
            f"tag-files [{tag}]: symlink points elsewhere, kept: "
            f"{_format_summary(skipped_other_target)}",
            "warn",
        )
    if skipped_unsafe:
        ctx.notify(
            f"tag-files [{tag}]: unsafe path, skipped: "
            f"{_format_summary(skipped_unsafe)}",
            "error",
        )
    if removed:
        prefix = "would unlink" if dry_run else "unlinked"
        ctx.status_update(f"tag-files [{tag}]: {prefix} {len(removed)} file(s)", "info")


def refresh(ctx: HookContext) -> None:
    base_dir = ctx.base_dir
    dry_run = bool(ctx.hook.config.get("dry_run", False))
    config_root = ctx.hook.config.get("root")
    root_dir = _resolve_root_dir(base_dir, config_root)

    if not root_dir.is_dir() or root_dir.is_symlink():
        if _root_is_explicit(config_root):
            ctx.notify(
                f"tag-files: root not a usable directory: {root_dir}",
                "warn",
            )
        return

    per_target_raw = ctx.change.get("per_target")
    per_target = per_target_raw if isinstance(per_target_raw, dict) else {}

    for target in ctx.targets:
        info = per_target.get(target.path) or per_target.get(str(target.path)) or {}
        tags = [str(t) for t in (info.get("current_tags") or []) if str(t).strip()]

        for tag in tags:
            src_root = _resolve_tag_root(root_dir, tag)
            if src_root is None:
                continue
            _link_tag_files(ctx, target.path, tag, src_root, dry_run=dry_run)

        _prune_orphan_links(ctx, target.path, root_dir, dry_run=dry_run)


def _last_known_links(project: Path, root_dir: Path) -> dict[str, dict[str, str]]:
    data = load_base_data(project)
    log_raw = data.get("log", {}) if isinstance(data, dict) else {}
    events = log_raw.get("events", []) if isinstance(log_raw, dict) else []
    if not isinstance(events, list):
        return {}
    root_resolved = root_dir.resolve()
    state: dict[str, dict[str, str]] = {}
    for entry in events:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("_event")
        rel = entry.get("rel")
        if not isinstance(rel, str) or not rel:
            continue
        if kind == "tag_files_linked":
            raw_target = entry.get("target")
            if not isinstance(raw_target, str) or not raw_target:
                continue
            try:
                Path(raw_target).resolve().relative_to(root_resolved)
            except (ValueError, OSError):
                continue
            tag = entry.get("tag")
            state[rel] = {
                "status": "linked",
                "target": raw_target,
                "tag": str(tag) if isinstance(tag, str) else "",
            }
        elif kind == "tag_files_unlinked":
            state.pop(rel, None)
    return state


def _prune_orphan_links(
    ctx: HookContext,
    project: Path,
    root_dir: Path,
    *,
    dry_run: bool,
) -> None:
    if not project.is_dir() or project.is_symlink():
        return
    known = _last_known_links(project, root_dir)
    if not known:
        return

    removed: list[str] = []
    skipped_not_link: list[str] = []
    skipped_other_target: list[str] = []

    for rel_str, info in sorted(known.items()):
        rel = Path(rel_str)
        dest = _safe_dest(project, rel)
        if dest is None:
            continue
        if not dest.is_symlink():
            if dest.exists():
                skipped_not_link.append(rel_str)
            continue
        expected = info["target"]
        actual = _symlink_target(dest)
        if actual != expected:
            skipped_other_target.append(rel_str)
            continue
        if Path(expected).exists():
            continue
        if dry_run:
            removed.append(rel_str)
            continue
        try:
            dest.unlink()
            removed.append(rel_str)
            ctx.add_event(
                project,
                "tag_files_unlinked",
                {
                    "tag": info.get("tag") or "",
                    "rel": rel_str,
                    "target": expected,
                    "reason": "orphan",
                },
            )
        except OSError as exc:
            ctx.notify(
                f"tag-files: unlink failed for {rel_str}: {exc}",
                "warn",
            )

    if not dry_run and removed:
        _prune_empty_dirs(project, removed)

    if skipped_not_link:
        ctx.log(
            f"tag-files refresh: replaced by real file, kept: "
            f"{_format_summary(skipped_not_link)}",
            "info",
        )
    if skipped_other_target:
        ctx.log(
            f"tag-files refresh: symlink points elsewhere, kept: "
            f"{_format_summary(skipped_other_target)}",
            "info",
        )
    if removed:
        prefix = "would prune" if dry_run else "pruned"
        ctx.log(f"tag-files refresh: {prefix} {len(removed)} orphan link(s)", "info")


def _prune_empty_dirs(project: Path, removed_rels: list[str]) -> None:
    seen: set[Path] = set()
    for rel_str in removed_rels:
        parts = Path(rel_str).parts[:-1]
        for depth in range(len(parts), 0, -1):
            sub = project / Path(*parts[:depth])
            seen.add(sub)
    project_resolved = project.resolve()
    for sub in sorted(seen, key=lambda p: len(p.parts), reverse=True):
        try:
            sub_resolved = sub.resolve(strict=False)
            sub_resolved.relative_to(project_resolved)
        except (ValueError, OSError):
            continue
        if sub_resolved == project_resolved:
            continue
        if not sub.is_dir() or sub.is_symlink():
            continue
        try:
            next(sub.iterdir())
            continue
        except StopIteration:
            pass
        except OSError:
            continue
        try:
            sub.rmdir()
        except OSError:
            pass
