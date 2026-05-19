from __future__ import annotations

from pathlib import Path

from homebase.core.models import ProjectRow
from homebase.ui.actions import bulk_confirm


def _row(
    path: Path,
    *,
    name: str | None = None,
    tags: list[str] | None = None,
    description: str = "",
    archived: bool = False,
    packed: bool = False,
    wip: bool = False,
    size_bytes: int = 0,
    archived_ts: int = 0,
    restore_target: Path | None = None,
) -> ProjectRow:
    return ProjectRow(
        path=path,
        name=name or path.name,
        branch="",
        dirty="",
        last="",
        src="",
        created="",
        tags=list(tags or []),
        properties=[],
        description=description,
        created_ts=0,
        last_ts=0,
        git_ts=0,
        opened_ts=0,
        is_fork=False,
        is_tmp=False,
        archived=archived,
        restore_target=restore_target,
        archived_ts=archived_ts,
        wip=wip,
        suffix=None,
        packed=packed,
        size_bytes=size_bytes,
    )


class _AppStub:
    def __init__(self, rows: list[ProjectRow], skipped: list[tuple[Path, str]] = ()) -> None:
        self._rows = list(rows)
        self._skipped = list(skipped)

    @staticmethod
    def _esc(text: object) -> str:
        return str(text).replace("[", "\\[").replace("]", "\\]")

    def _find_row(self, path: Path):
        for idx, row in enumerate(self._rows):
            if row.path == path:
                return self._rows, idx
        return None

    def _preflight_bulk_action(self, _action: str, paths: list[Path]):
        skipped_paths = {p for p, _ in self._skipped}
        runnable = [p for p in paths if p not in skipped_paths]
        return runnable, list(self._skipped)

    def _preflight_skip_summary(self, skipped: list[tuple[Path, str]]) -> str:
        return ", ".join(f"{r}" for _, r in skipped)


def _is_under(p: Path, base: Path) -> bool:
    try:
        p.relative_to(base)
        return True
    except ValueError:
        return False


def _restore_target_factory(base_dir: Path, archived_path: Path) -> Path:
    return base_dir / archived_path.name.replace("2024-01-01_", "")


def test_archive_confirm_includes_destination_and_date_source(tmp_path: Path) -> None:
    base = tmp_path
    src = base / "myproj"
    src.mkdir()
    # Touch one regular file so mtime detection has something to find.
    (src / "README.md").write_text("hello", encoding="utf-8")
    row = _row(src)
    app = _AppStub([row])
    _title, body = bulk_confirm.build_bulk_confirm_payload(
        app,
        "archive",
        [src],
        base_dir=base,
        archived_restore_target=_restore_target_factory,
        is_under=_is_under,
    )
    assert "target preview" in body
    # Destination path under _archive/<year>/<YYYY-MM-DD>_<stem> shows up.
    assert "_archive/" in body
    assert "myproj" in body
    # Some date-source label is present (mtime, name, git, or fallback).
    assert any(token in body for token in ("mtime", "today", "name", "git HEAD"))


def test_archive_confirm_marks_today_fallback(tmp_path: Path) -> None:
    base = tmp_path
    src = base / "no_clues"
    src.mkdir()
    # No files, no .git → detection returns None → today fallback path.
    row = _row(src)
    app = _AppStub([row])
    _title, body = bulk_confirm.build_bulk_confirm_payload(
        app,
        "archive",
        [src],
        base_dir=base,
        archived_restore_target=_restore_target_factory,
        is_under=_is_under,
    )
    assert "today fallback" in body
    # The fallback is colored yellow to draw the eye.
    assert "[yellow]" in body


def test_delete_confirm_shows_tags_and_description(tmp_path: Path) -> None:
    base = tmp_path
    path = base / "secret"
    path.mkdir()
    row = _row(
        path,
        tags=["mine", "ops"],
        description="critical readme",
        size_bytes=2048,
    )
    app = _AppStub([row])
    _title, body = bulk_confirm.build_bulk_confirm_payload(
        app,
        "delete",
        [path],
        base_dir=base,
        archived_restore_target=_restore_target_factory,
        is_under=_is_under,
    )
    assert "mine, ops" in body
    assert "critical readme" in body
    assert "2.0 KB" in body
    # Delete keeps its irreversibility warning.
    assert "cannot be undone" in body


def test_delete_confirm_marks_archived_and_restore_target(tmp_path: Path) -> None:
    base = tmp_path
    path = base / "_archive" / "2024" / "2024-01-01_proj"
    path.mkdir(parents=True)
    restore = base / "proj"
    row = _row(
        path,
        archived=True,
        restore_target=restore,
        size_bytes=0,
    )
    app = _AppStub([row])
    _title, body = bulk_confirm.build_bulk_confirm_payload(
        app,
        "delete",
        [path],
        base_dir=base,
        archived_restore_target=_restore_target_factory,
        is_under=_is_under,
    )
    assert "archived" in body
    assert str(restore) in body


def test_restore_confirm_marks_conflict_per_row(tmp_path: Path) -> None:
    base = tmp_path
    archive_root = base / "_archive" / "2024"
    archive_root.mkdir(parents=True)
    src = archive_root / "2024-01-01_proj"
    src.mkdir()
    # Pre-create the would-be restore target so conflict triggers.
    (base / "proj").mkdir()
    row = _row(
        src,
        archived=True,
        restore_target=base / "proj",
        archived_ts=1_700_000_000,
    )
    app = _AppStub([row])
    _title, body = bulk_confirm.build_bulk_confirm_payload(
        app,
        "restore",
        [src],
        base_dir=base,
        archived_restore_target=_restore_target_factory,
        is_under=_is_under,
    )
    assert "target exists" in body
    # Archived date is surfaced per row.
    assert "archived:" in body


def test_pack_confirm_shows_resulting_name(tmp_path: Path) -> None:
    base = tmp_path
    src = base / "_archive" / "2024" / "2024-01-01_proj"
    src.mkdir(parents=True)
    row = _row(src, size_bytes=1024 * 1024)
    app = _AppStub([row])
    _title, body = bulk_confirm.build_bulk_confirm_payload(
        app,
        "pack",
        [src],
        base_dir=base,
        archived_restore_target=_restore_target_factory,
        is_under=_is_under,
        is_packed_archive_path=lambda p: p.suffix == ".tgz",
    )
    assert "2024-01-01_proj.tgz" in body
    assert "1.0 MB" in body


def test_unpack_confirm_shows_resulting_dir(tmp_path: Path) -> None:
    base = tmp_path
    src = base / "_archive" / "2024" / "2024-01-01_proj.tgz"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"")
    row = _row(src, packed=True, size_bytes=512)
    app = _AppStub([row])
    _title, body = bulk_confirm.build_bulk_confirm_payload(
        app,
        "unpack",
        [src],
        base_dir=base,
        archived_restore_target=_restore_target_factory,
        is_under=_is_under,
        is_packed_archive_path=lambda p: p.suffix == ".tgz",
    )
    # The .tgz source is mapped to the bare directory name.
    assert "_archive/2024/2024-01-01_proj.tgz" in body
    assert "_archive/2024/2024-01-01_proj" in body
    assert "[dim]→[/]" in body
