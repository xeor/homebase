from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from homebase.commands import basic as commands_basic


@dataclass
class Row:
    name: str
    branch: str
    dirty: str
    last: str
    tags: list[str]
    git_ts: int = 0


def test_cmd_status_prints_rows(capsys) -> None:
    rows = [Row("proj", "main", "*", "today", ["api"]) ]
    rc = commands_basic.cmd_status(Path("."), collect_projects=lambda _b: rows)
    out = capsys.readouterr().out
    assert rc == 0
    assert "proj" in out


def test_cmd_recent_uses_sort_and_formatter(capsys) -> None:
    rows = [Row("proj", "main", "", "-", [], git_ts=1)]
    rc = commands_basic.cmd_recent(
        Path("."),
        collect_projects=lambda _b: rows,
        sort_rows=lambda values, _mode: values,
        fmt_ymd=lambda _ts: "2026-01-01",
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "2026-01-01" in out
