from __future__ import annotations

from homebase.core.changelog import (
    ChangelogEntry,
    entries_since,
    parse_changelog,
    semver_tuple,
)

_SAMPLE = """# Changelog

## 0.5.1 - 2026-06-25

- worktree support
- hooks

## 0.5.0 - 2026-06-24

First version.

- version tracking
"""


def test_parse_changelog_no_commit_hash() -> None:
    entries = parse_changelog(_SAMPLE)
    assert [e.version for e in entries] == ["0.5.1", "0.5.0"]
    assert [e.date for e in entries] == ["2026-06-25", "2026-06-24"]
    assert "worktree support" in entries[0].body
    assert "version tracking" in entries[1].body


def test_parse_changelog_rejects_old_commit_heading() -> None:
    text = "# Changelog\n\n## 0.5.1 (32836ad) - 2026-06-25\n\n- x\n"
    assert parse_changelog(text) == []


def test_entries_since_returns_strictly_newer() -> None:
    entries = parse_changelog(_SAMPLE)
    assert [e.version for e in entries_since(entries, "0.5.0")] == ["0.5.1"]
    assert entries_since(entries, "0.5.1") == []
    assert [e.version for e in entries_since(entries, None)] == ["0.5.1"]


def test_semver_tuple() -> None:
    assert semver_tuple("1.2.3") == (1, 2, 3)
    assert semver_tuple("0.5.1+dev") == (0, 5, 1)
    assert semver_tuple("garbage") == (0, 0, 0)


def test_changelog_entry_has_no_commit_field() -> None:
    assert set(ChangelogEntry.__dataclass_fields__) == {"version", "date", "body"}
