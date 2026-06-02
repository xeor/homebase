from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from homebase.ui.sync import indicator_queries as iq


class _Row:
    """Minimal stand-in for ``ProjectRow`` — only the attributes the
    query helpers actually look at."""

    def __init__(self, path: Path, *, packed: bool = False) -> None:
        self.path = path
        self.packed = packed


class _Pane:
    def __init__(self, command: str) -> None:
        self.command = command


class _App:
    def __init__(self, *, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.open_pane_count_by_project: dict[Path, int] = {}
        self.open_panes_by_project: dict[Path, list[_Pane]] = {}
        self.active_rows: list[_Row] = []
        self.archived_rows: list[_Row] = []
        self.metadata_health_cache: dict[Path, tuple[str, str, float]] = {}


# ---- evaluate_query_paths -------------------------------------------


def test_evaluate_query_paths_tmux_open_panes_filters_zero_counts(tmp_path: Path) -> None:
    app = _App(base_dir=tmp_path)
    a = tmp_path / "a"
    b = tmp_path / "b"
    c = tmp_path / "c"
    app.open_pane_count_by_project = {a: 2, b: 0, c: 1}
    out = iq.evaluate_query_paths(app, {"type": "tmux_open_panes"})
    assert out == {a, c}


def test_evaluate_query_paths_tmux_open_panes_empty_when_no_panes(tmp_path: Path) -> None:
    app = _App(base_dir=tmp_path)
    assert iq.evaluate_query_paths(app, {"type": "tmux_open_panes"}) == set()


def test_evaluate_query_paths_tmux_editor_commands_matches_any_pane(tmp_path: Path) -> None:
    app = _App(base_dir=tmp_path)
    a = tmp_path / "a"
    b = tmp_path / "b"
    app.open_panes_by_project = {
        a: [_Pane("zsh"), _Pane("nvim")],
        b: [_Pane("bash"), _Pane("less")],
    }
    out = iq.evaluate_query_paths(
        app,
        {"type": "tmux_editor_commands", "commands": ["nvim", "vim", "  helix  "]},
    )
    assert out == {a}


def test_evaluate_query_paths_tmux_editor_commands_lowercases_match(tmp_path: Path) -> None:
    app = _App(base_dir=tmp_path)
    a = tmp_path / "a"
    app.open_panes_by_project = {a: [_Pane("NVIM")]}
    out = iq.evaluate_query_paths(
        app, {"type": "tmux_editor_commands", "commands": ["nvim"]},
    )
    assert out == {a}


def test_evaluate_query_paths_tmux_editor_commands_ignores_blank_entries(tmp_path: Path) -> None:
    app = _App(base_dir=tmp_path)
    a = tmp_path / "a"
    app.open_panes_by_project = {a: [_Pane("nvim")]}
    out = iq.evaluate_query_paths(
        app, {"type": "tmux_editor_commands", "commands": ["", "   ", "nvim"]},
    )
    assert out == {a}


def test_evaluate_query_paths_unknown_type_returns_empty(tmp_path: Path) -> None:
    app = _App(base_dir=tmp_path)
    assert iq.evaluate_query_paths(app, {"type": "nope"}) == set()
    assert iq.evaluate_query_paths(app, {}) == set()


# ---- _sqlite_recent_paths -------------------------------------------


def _make_value_table(db_path: Path, values: list[str]) -> None:
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("create table ItemTable (key text primary key, value text)")
        for i, value in enumerate(values):
            con.execute("insert into ItemTable values (?, ?)", (f"k{i}", value))
        con.commit()
    finally:
        con.close()


def test_sqlite_recent_paths_returns_empty_without_db_path(tmp_path: Path) -> None:
    assert iq._sqlite_recent_paths({}, base_dir=tmp_path) == []
    assert iq._sqlite_recent_paths({"db_path": ""}, base_dir=tmp_path) == []


def test_sqlite_recent_paths_returns_empty_when_db_missing(tmp_path: Path) -> None:
    out = iq._sqlite_recent_paths(
        {"db_path": str(tmp_path / "missing.db")},
        base_dir=tmp_path,
    )
    assert out == []


def test_sqlite_recent_paths_extracts_plain_file_uris(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    target = tmp_path / "proj" / "file.txt"
    _make_value_table(db, [f'"file://{target.as_posix()}"'])
    paths = iq._sqlite_recent_paths({"db_path": str(db)}, base_dir=tmp_path)
    assert target in paths


def test_sqlite_recent_paths_decodes_percent_escaped(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    target = tmp_path / "my project" / "doc.md"
    encoded = "file://" + target.as_posix().replace(" ", "%20")
    _make_value_table(db, [f'"{encoded}"'])
    paths = iq._sqlite_recent_paths({"db_path": str(db)}, base_dir=tmp_path)
    assert target in paths


def test_sqlite_recent_paths_unwraps_json_payload(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    target = tmp_path / "p" / "x.txt"
    payload = json.dumps({"recent": [f"file://{target.as_posix()}"]})
    _make_value_table(db, [payload])
    paths = iq._sqlite_recent_paths({"db_path": str(db)}, base_dir=tmp_path)
    assert target in paths


def test_sqlite_recent_paths_handles_multiple_uris_in_one_value(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    a = tmp_path / "a" / "f.txt"
    b = tmp_path / "b" / "g.txt"
    value = f'"file://{a.as_posix()}","file://{b.as_posix()}"'
    _make_value_table(db, [value])
    paths = iq._sqlite_recent_paths({"db_path": str(db)}, base_dir=tmp_path)
    assert a in paths and b in paths


def test_sqlite_recent_paths_honors_where_like_filter(tmp_path: Path) -> None:
    """Rows whose value doesn't match ``where_like`` aren't even
    fetched. Use a pattern that excludes everything to prove the
    parameter is used."""
    db = tmp_path / "history.db"
    target = tmp_path / "x.txt"
    _make_value_table(db, [f'"file://{target.as_posix()}"'])
    paths = iq._sqlite_recent_paths(
        {"db_path": str(db), "where_like": "%no-match%"},
        base_dir=tmp_path,
    )
    assert paths == []


def test_sqlite_recent_paths_custom_table_and_column(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    target = tmp_path / "x.txt"
    con = sqlite3.connect(str(db))
    try:
        con.execute("create table recent (uri text)")
        con.execute(
            "insert into recent values (?)",
            (f'"file://{target.as_posix()}"',),
        )
        con.commit()
    finally:
        con.close()
    paths = iq._sqlite_recent_paths(
        {"db_path": str(db), "table": "recent", "value_column": "uri"},
        base_dir=tmp_path,
    )
    assert target in paths


def test_sqlite_recent_paths_skips_value_without_file_scheme(tmp_path: Path) -> None:
    """A value with no ``file://`` substring at all yields no paths,
    but the row is still selected by the LIKE filter (we control the
    filter to widen the match)."""
    db = tmp_path / "history.db"
    _make_value_table(db, ['"https://example.com/something"'])
    paths = iq._sqlite_recent_paths(
        {"db_path": str(db), "where_like": "%example%"}, base_dir=tmp_path,
    )
    assert paths == []


def test_sqlite_recent_paths_returns_empty_on_sqlite_error(tmp_path: Path) -> None:
    bogus = tmp_path / "not.db"
    bogus.write_bytes(b"not a sqlite database")
    paths = iq._sqlite_recent_paths({"db_path": str(bogus)}, base_dir=tmp_path)
    assert paths == []


# ---- evaluate_query_paths(sqlite_recent_paths) ----------------------


def test_evaluate_query_paths_sqlite_matches_project_root(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    inside = proj / "src" / "main.py"
    inside.parent.mkdir(parents=True)
    inside.write_text("x")
    db = tmp_path / "h.db"
    _make_value_table(db, [f'"file://{inside.as_posix()}"'])

    app = _App(base_dir=tmp_path)
    app.active_rows = [_Row(proj)]
    out = iq.evaluate_query_paths(
        app, {"type": "sqlite_recent_paths", "db_path": str(db)},
    )
    assert out == {proj.resolve()}


def test_evaluate_query_paths_sqlite_no_match_when_outside_any_root(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    outside = tmp_path / "other" / "f.txt"
    outside.parent.mkdir(parents=True)
    outside.write_text("x")
    db = tmp_path / "h.db"
    _make_value_table(db, [f'"file://{outside.as_posix()}"'])

    app = _App(base_dir=tmp_path)
    app.active_rows = [_Row(proj)]
    out = iq.evaluate_query_paths(
        app, {"type": "sqlite_recent_paths", "db_path": str(db)},
    )
    assert out == set()


# ---- evaluate_query_match -------------------------------------------


def test_evaluate_query_match_packed_archive(tmp_path: Path) -> None:
    app = _App(base_dir=tmp_path)
    packed = _Row(tmp_path / "p", packed=True)
    unpacked = _Row(tmp_path / "u", packed=False)
    q = {"type": "packed_archive"}
    assert iq.evaluate_query_match(app, packed, q) is True
    assert iq.evaluate_query_match(app, unpacked, q) is False


def test_evaluate_query_match_metadata_health_warning(tmp_path: Path) -> None:
    app = _App(base_dir=tmp_path)
    row = _Row(tmp_path / "x")
    # cached: (level, message, expires_at). Future expiry → fresh.
    app.metadata_health_cache[row.path] = ("warning", "msg", time.time() + 60)
    assert iq.evaluate_query_match(
        app, row, {"type": "metadata_health", "level": "warning"},
    ) is True
    assert iq.evaluate_query_match(
        app, row, {"type": "metadata_health", "level": "error"},
    ) is False


def test_evaluate_query_match_metadata_health_unknown_level(tmp_path: Path) -> None:
    app = _App(base_dir=tmp_path)
    row = _Row(tmp_path / "x")
    app.metadata_health_cache[row.path] = ("warning", "msg", time.time() + 60)
    assert iq.evaluate_query_match(
        app, row, {"type": "metadata_health", "level": "info"},
    ) is False


def test_evaluate_query_match_metadata_health_missing_cache(tmp_path: Path) -> None:
    app = _App(base_dir=tmp_path)
    row = _Row(tmp_path / "x")
    assert iq.evaluate_query_match(
        app, row, {"type": "metadata_health", "level": "warning"},
    ) is False


def test_evaluate_query_match_metadata_health_stale_cache(tmp_path: Path) -> None:
    """A cache entry past its expiry must not count as a current
    issue — the indicator should wait for a refreshed health probe."""
    app = _App(base_dir=tmp_path)
    row = _Row(tmp_path / "x")
    app.metadata_health_cache[row.path] = ("error", "msg", 0.0)
    assert iq.evaluate_query_match(
        app, row, {"type": "metadata_health", "level": "error"},
    ) is False


def test_evaluate_query_match_unknown_type(tmp_path: Path) -> None:
    app = _App(base_dir=tmp_path)
    row = _Row(tmp_path / "x")
    assert iq.evaluate_query_match(app, row, {"type": "nope"}) is False
    assert iq.evaluate_query_match(app, row, {}) is False


def test_evaluate_query_match_delegates_path_types(tmp_path: Path) -> None:
    """``tmux_open_panes`` / ``tmux_editor_commands`` /
    ``sqlite_recent_paths`` all reuse ``evaluate_query_paths`` —
    a row matches iff its path is in the returned set."""
    app = _App(base_dir=tmp_path)
    p = tmp_path / "p"
    app.open_pane_count_by_project = {p: 1}
    row_in = _Row(p)
    row_out = _Row(tmp_path / "other")
    q = {"type": "tmux_open_panes"}
    assert iq.evaluate_query_match(app, row_in, q) is True
    assert iq.evaluate_query_match(app, row_out, q) is False


# ---- cache_due ------------------------------------------------------


def test_cache_due_true_at_or_past_expiry(monkeypatch) -> None:
    monkeypatch.setattr(iq.time, "time", lambda: 100.0)
    assert iq.cache_due(100.0) is True
    assert iq.cache_due(50.0) is True


def test_cache_due_false_when_still_fresh(monkeypatch) -> None:
    monkeypatch.setattr(iq.time, "time", lambda: 100.0)
    assert iq.cache_due(101.0) is False
    assert iq.cache_due(1e12) is False
