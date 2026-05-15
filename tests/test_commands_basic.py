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
