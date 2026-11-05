from __future__ import annotations

from pathlib import Path

from homebase.core.constants import ARCHIVE_DIR_NAME
from homebase.core.models import ProjectRow
from homebase.workspace import rows


def _row(*, properties: list[str] | None = None) -> ProjectRow:
    return ProjectRow(
        path=Path("/tmp/demo"),
        name="demo",
        branch="main",
        dirty="",
        last="2026-01-01",
        src="git",
        created="2026-01-01",
        tags=["cli"],
        properties=properties or [],
        description="demo project",
        created_ts=1,
        last_ts=1,
        git_ts=1,
        opened_ts=1,
        is_fork=False,
        is_tmp=False,
        archived=False,
        restore_target=None,
        archived_ts=0,
        wip=False,
        suffix=None,
    )


def test_match_query_matches_property_token() -> None:
    assert rows.match_query(_row(properties=["act"]), "act")


def test_match_query_matches_path_text() -> None:
    assert rows.match_query(_row(), "tmp/demo")


def test_archived_restore_target_handles_new_packed_name() -> None:
    base_dir = Path("/tmp/base")
    archived_entry = base_dir / ARCHIVE_DIR_NAME / "2026-05-11_demo.tgz"
    target = rows.archived_restore_target(base_dir, archived_entry)
    assert target == base_dir / "demo"


def test_archived_restore_target_strips_year_subdir() -> None:
    base_dir = Path("/tmp/base")
    archived_entry = base_dir / ARCHIVE_DIR_NAME / "2024" / "2024-05-01_demo"
    target = rows.archived_restore_target(base_dir, archived_entry)
    assert target == base_dir / "demo"


def test_archived_restore_target_strips_year_for_packed() -> None:
    base_dir = Path("/tmp/base")
    archived_entry = base_dir / ARCHIVE_DIR_NAME / "2024" / "2024-05-01_demo.tgz"
    target = rows.archived_restore_target(base_dir, archived_entry)
    assert target == base_dir / "demo"


def test_archived_restore_target_strips_prefix_with_zero_segments() -> None:
    base_dir = Path("/tmp/base")
    archived_entry = base_dir / ARCHIVE_DIR_NAME / "2003" / "2003-00-00_ghost"
    target = rows.archived_restore_target(base_dir, archived_entry)
    assert target == base_dir / "ghost"


def test_packed_meta_memo_persists_and_seeds_once(tmp_path: Path) -> None:
    from homebase.cache.api import cache_load_packed_meta, cache_save_packed_meta
    from homebase.core import packed_meta
    from homebase.workspace import rows as rows_mod

    packed_meta._PACKED_NEW.clear()
    packed_meta._PACKED_SEED.clear()
    rows_mod._PACKED_MEMO_SEEDED.discard(tmp_path)
    packed_meta._packed_memo_record(("/x.tgz", 1, 2), "x/.base.yaml", "tags: []\n")
    rows_mod._persist_packed_meta(tmp_path)
    assert cache_load_packed_meta(tmp_path) == [("/x.tgz", 1, 2, "x/.base.yaml", "tags: []\n")]
    rows_mod._persist_packed_meta(tmp_path)  # nothing new: no-op

    rows_mod._seed_packed_meta(tmp_path)
    assert packed_meta._PACKED_SEED == {("/x.tgz", 1, 2): ("x/.base.yaml", "tags: []\n")}
    # Seeded once per process.
    cache_save_packed_meta(tmp_path, [("/y.tgz", 1, 2, None, None)])
    rows_mod._seed_packed_meta(tmp_path)
    assert ("/y.tgz", 1, 2) not in packed_meta._PACKED_SEED
    packed_meta._PACKED_SEED.clear()
