from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from homebase.commands import basic as commands_basic


@dataclass
class Row:
    name: str
    branch: str = ""
    dirty: str = ""
    last: str = ""
    last_ts: int = 0
    tags: list[str] = field(default_factory=list)
    size_bytes: int = 0
    git_ts: int = 0
    created_ts: int = 0
    opened_ts: int = 0
    wip: bool = False
    worktree_of: str = ""
    src: str = ""
    path: str = ""
    description: str = ""
    properties: list[str] = field(default_factory=list)


def _stub_filter(expr: str):
    """Mimics ``compile_filter_expr``: returns (predicate, error). Our
    stub treats the expression as a substring match on row.name and
    rejects "!bad" outright so we can exercise the error path."""
    if expr == "!bad":
        return (lambda _r: False, "syntax: !bad")
    needle = expr.lower()

    def pred(row):
        return needle in row.name.lower()

    return (pred, None)


def _stub_loader(active, archived=None):
    return lambda _bd: (list(active), list(archived or []), 0)


def test_cmd_ls_default_prints_names_only_sorted(capsys) -> None:
    """No flags → one name per line, alphabetically sorted, from the
    cache loader. Nothing else on stdout."""
    rows = [Row("zeta"), Row("alpha"), Row("middle")]
    rc = commands_basic.cmd_ls(
        Path("."),
        cache_load_rows=_stub_loader(rows),
        compile_filter_expr=_stub_filter,
        fmt_ymd=lambda _ts: "x",
        fmt_size_human=lambda _b: "x",
    )
    out = capsys.readouterr().out.splitlines()
    assert rc == 0
    assert out == ["alpha", "middle", "zeta"]


def test_cmd_ls_filter_narrows_results(capsys) -> None:
    rows = [Row("alpha"), Row("alpine"), Row("beta")]
    rc = commands_basic.cmd_ls(
        Path("."),
        cache_load_rows=_stub_loader(rows),
        compile_filter_expr=_stub_filter,
        fmt_ymd=lambda _ts: "x",
        fmt_size_human=lambda _b: "x",
        filter_expr="alp",
    )
    out = capsys.readouterr().out.splitlines()
    assert rc == 0
    assert out == ["alpha", "alpine"]


def test_cmd_ls_bad_filter_returns_nonzero(capsys) -> None:
    rc = commands_basic.cmd_ls(
        Path("."),
        cache_load_rows=_stub_loader([Row("any")]),
        compile_filter_expr=_stub_filter,
        fmt_ymd=lambda _ts: "x",
        fmt_size_human=lambda _b: "x",
        filter_expr="!bad",
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "syntax: !bad" in err


def test_cmd_ls_long_includes_modified_size_tags(capsys) -> None:
    rows = [
        Row("alpha", last_ts=1234, size_bytes=2048, tags=["work", "wip"]),
    ]
    rc = commands_basic.cmd_ls(
        Path("."),
        cache_load_rows=_stub_loader(rows),
        compile_filter_expr=_stub_filter,
        fmt_ymd=lambda _ts: "2026-05-15",
        fmt_size_human=lambda _b: "2.0 KB",
        long_format=True,
    )
    out = capsys.readouterr().out
    assert rc == 0
    # Header row + data row both present, with the expected fields.
    assert "NAME" in out and "MODIFIED" in out and "SIZE" in out and "TAGS" in out
    assert "alpha" in out and "2026-05-15" in out and "2.0 KB" in out
    assert "work,wip" in out


def test_cmd_ls_archived_lists_archive_set(capsys) -> None:
    rc = commands_basic.cmd_ls(
        Path("."),
        cache_load_rows=_stub_loader([Row("active1")], [Row("arch1")]),
        compile_filter_expr=_stub_filter,
        fmt_ymd=lambda _ts: "x",
        fmt_size_human=lambda _b: "x",
        show_archived=True,
    )
    out = capsys.readouterr().out.splitlines()
    assert rc == 0
    assert out == ["arch1"]


def test_cmd_ls_extra_column_flags_render_their_fields(capsys) -> None:
    """Every ``with_*`` flag must contribute its column to the long
    output and pull the right field off the row. Asserting the
    presence of the field values (not the exact header positions)
    keeps the test resilient to future column-order tweaks."""
    rows = [
        Row(
            "alpha",
            last_ts=1234,
            size_bytes=2048,
            tags=["t1"],
            created_ts=100,
            opened_ts=200,
            wip=True,
            worktree_of="origin-proj",
            src="origin-src",
            path="/abs/projects/alpha",
            description="long form description",
            properties=["p1", "p2"],
        ),
    ]

    def _fmt_ymd(ts: int) -> str:
        return f"DATE-{ts}"

    rc = commands_basic.cmd_ls(
        Path("."),
        cache_load_rows=_stub_loader(rows),
        compile_filter_expr=_stub_filter,
        fmt_ymd=_fmt_ymd,
        fmt_size_human=lambda _b: "2.0 KB",
        with_created=True,
        with_active=True,
        with_wip=True,
        with_worktree_of=True,
        with_src=True,
        with_path=True,
        with_description=True,
        with_props=True,
    )
    out = capsys.readouterr().out
    assert rc == 0
    # Every flag's header must appear.
    for header in (
        "NAME", "CREATED", "MODIFIED", "ACTIVE", "WIP", "SIZE",
        "WORKTREE-OF", "SRC", "PATH", "DESCRIPTION", "TAGS", "PROPS",
    ):
        assert header in out, f"missing header {header!r}: {out!r}"
    # And each value must appear somewhere on the data row.
    for value in (
        "DATE-100", "DATE-1234", "DATE-200", "wip", "origin-proj",
        "origin-src", "/abs/projects/alpha",
        "long form description", "t1", "p1,p2",
    ):
        assert value in out, f"missing value {value!r}: {out!r}"


def test_cmd_ls_extra_flag_triggers_long_format_without_dash_l(
    capsys,
) -> None:
    """``b ls --path`` alone (no ``-l``) must switch into long-format
    rendering; otherwise the user can't opt into a single extra
    column without also typing ``-l``."""
    rows = [Row("alpha", path="/abs/alpha")]
    rc = commands_basic.cmd_ls(
        Path("."),
        cache_load_rows=_stub_loader(rows),
        compile_filter_expr=_stub_filter,
        fmt_ymd=lambda _ts: "-",
        fmt_size_human=lambda _b: "0 B",
        with_path=True,
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "NAME" in out
    assert "PATH" in out
    assert "/abs/alpha" in out


def test_cmd_ls_with_git_calls_enricher_then_shows_branch(capsys) -> None:
    """``--git`` opts into the slow refresh path: we call the injected
    enricher, then render the BRANCH column."""
    rows = [Row("repo")]
    seen: list[list[Row]] = []
    def enrich(rs):
        seen.append(list(rs))
        rs[0].branch = "main"
        rs[0].dirty = "*"
    rc = commands_basic.cmd_ls(
        Path("."),
        cache_load_rows=_stub_loader(rows),
        compile_filter_expr=_stub_filter,
        fmt_ymd=lambda _ts: "x",
        fmt_size_human=lambda _b: "x",
        enrich_git=enrich,
        with_git=True,
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert seen and seen[0][0].name == "repo"
    assert "BRANCH" in out
    assert "main*" in out


def _parse_json_out(capsys) -> list[dict]:
    import json as _json
    return _json.loads(capsys.readouterr().out)


def test_cmd_json_default_emits_active_rows_only(capsys) -> None:
    """No flags → JSON array of *active* rows only, no archived
    leakage, no ``is_archived`` field."""
    active = [Row("alpha", path="/a/alpha"), Row("beta", path="/a/beta")]
    archived = [Row("ghost", path="/a/ghost")]
    rc = commands_basic.cmd_json(
        Path("."),
        cache_load_rows=_stub_loader(active, archived),
        compile_filter_expr=_stub_filter,
    )
    assert rc == 0
    payload = _parse_json_out(capsys)
    assert [r["name"] for r in payload] == ["alpha", "beta"]
    assert all("is_archived" not in r for r in payload)


def test_cmd_json_archived_flag_merges_and_marks(capsys) -> None:
    """``--archived`` returns active + archived in one list, sorted
    by name; archived entries get ``is_archived: true`` so consumers
    can tell them apart, active entries do *not* get the field."""
    active = [Row("alpha", path="/a/alpha")]
    archived = [Row("beta", path="/a/beta"), Row("gamma", path="/a/gamma")]
    rc = commands_basic.cmd_json(
        Path("."),
        cache_load_rows=_stub_loader(active, archived),
        compile_filter_expr=_stub_filter,
        include_archived=True,
    )
    assert rc == 0
    payload = _parse_json_out(capsys)
    by_name = {r["name"]: r for r in payload}
    assert set(by_name) == {"alpha", "beta", "gamma"}
    assert "is_archived" not in by_name["alpha"]
    assert by_name["beta"]["is_archived"] is True
    assert by_name["gamma"]["is_archived"] is True


def test_cmd_json_archived_only_emits_archive_set(capsys) -> None:
    """``--archived-only`` swaps the source set: emit *only* archived
    rows, no active leakage. ``is_archived`` is unnecessary since
    every row is archived."""
    active = [Row("alpha", path="/a/alpha")]
    archived = [Row("beta", path="/a/beta")]
    rc = commands_basic.cmd_json(
        Path("."),
        cache_load_rows=_stub_loader(active, archived),
        compile_filter_expr=_stub_filter,
        archived_only=True,
    )
    assert rc == 0
    payload = _parse_json_out(capsys)
    assert [r["name"] for r in payload] == ["beta"]
    assert all("is_archived" not in r for r in payload)


def test_cmd_json_filter_narrows_results(capsys) -> None:
    """Filter expression compiles via the injected helper and
    narrows the payload before serialization — same syntax as
    ``b ls``."""
    rows = [
        Row("alpha-infra", path="/a/alpha", tags=["infra"]),
        Row("beta-app", path="/a/beta", tags=["app"]),
    ]
    rc = commands_basic.cmd_json(
        Path("."),
        cache_load_rows=_stub_loader(rows),
        compile_filter_expr=_stub_filter,
        filter_expr="alpha",
    )
    assert rc == 0
    payload = _parse_json_out(capsys)
    assert [r["name"] for r in payload] == ["alpha-infra"]


def test_cmd_json_bad_filter_returns_nonzero(capsys) -> None:
    """Malformed filter → rc=2 with error on stderr, no JSON on
    stdout. Matches the ``b ls`` behavior so script consumers can
    rely on rc."""
    rc = commands_basic.cmd_json(
        Path("."),
        cache_load_rows=_stub_loader([Row("any", path="/p")]),
        compile_filter_expr=_stub_filter,
        filter_expr="!bad",
    )
    assert rc == 2
    captured = capsys.readouterr()
    assert "syntax: !bad" in captured.err
    assert captured.out == ""


def test_cmd_json_payload_omits_internal_cache_fields(capsys) -> None:
    """Internal cache bookkeeping (haystack_lower, tags_lower,
    cache_age_s, last_cached_ts, …) must *not* leak into the JSON —
    consumers don't need it and those fields aren't stable across
    runs."""
    rc = commands_basic.cmd_json(
        Path("."),
        cache_load_rows=_stub_loader([Row("alpha", path="/p", tags=["t1"])]),
        compile_filter_expr=_stub_filter,
    )
    assert rc == 0
    payload = _parse_json_out(capsys)
    for forbidden in (
        "haystack_lower", "tags_lower", "cache_age_s",
        "last_cached_ts", "last_reconciled_ts", "stale",
    ):
        assert forbidden not in payload[0]


def test_cmd_recent_uses_sort_and_formatter(capsys) -> None:
    rows = [Row("proj", "main", "", "-", git_ts=1)]
    rc = commands_basic.cmd_recent(
        Path("."),
        collect_projects=lambda _b: rows,
        sort_rows=lambda values, _mode: values,
        fmt_ymd=lambda _ts: "2026-01-01",
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "2026-01-01" in out
