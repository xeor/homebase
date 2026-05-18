from __future__ import annotations

import re
from datetime import datetime, timezone

from homebase.archive import date_detect
from homebase.commands import workspace as commands_workspace
from homebase.core import utils as core_utils

_TZ = timezone.utc
_YEAR_RE = re.compile(r"^\d{4}$")
_MARKER = ".base.yaml"


def _stub_deps(*, prompt_yes_no=None, read_line=None, confirm=None) -> dict:
    return dict(
        env_base_dir_key="HOMEBASE_FIX_TEST_BASE",
        archive_dir_name="_archive",
        archive_year_re=_YEAR_RE,
        archive_tz=_TZ,
        is_under=core_utils.is_under,
        base_marker_file=_MARKER,
        prompt_yes_no=prompt_yes_no or (lambda _q, d: d),
        parse_archive_timestamp=lambda v: core_utils.parse_archive_timestamp(v, _TZ),
        archive_iso_from_ts=lambda ts, tz: core_utils.archive_iso_from_ts(ts, tz),
        detect_folder_date=date_detect.detect_folder_date,
        parse_user_date=date_detect.parse_user_date,
        strip_date_prefix=date_detect.strip_date_prefix,
        ensure_base_marker=lambda p: (p / _MARKER).touch(),
        confirm=confirm or (lambda: None),
        read_line=read_line or (lambda _q: ""),
    )


def _run(base_dir, monkeypatch, **kwargs):
    monkeypatch.setenv("HOMEBASE_FIX_TEST_BASE", str(base_dir))
    return commands_workspace.cmd_fix(**kwargs, **_stub_deps(**kwargs.pop("dep_overrides", {})))


def test_fix_creates_marker_under_base(tmp_path, monkeypatch):
    base = tmp_path / "base"
    proj = base / "proj"
    proj.mkdir(parents=True)
    rc = _run(
        base, monkeypatch,
        paths=[str(proj)],
        include=set(commands_workspace.FIX_KINDS),
        yes=False,
    )
    assert rc == 0
    assert (proj / _MARKER).is_file()


def test_fix_skips_outside_base(tmp_path, monkeypatch, capsys):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    rc = _run(
        base, monkeypatch,
        paths=[str(outside)],
        include=set(commands_workspace.FIX_KINDS),
        yes=False,
    )
    assert rc == 0
    assert "not under base" in capsys.readouterr().err
    assert not (outside / _MARKER).exists()


def test_fix_multi_path_runs_each(tmp_path, monkeypatch):
    base = tmp_path / "base"
    a = base / "a"
    b = base / "b"
    a.mkdir(parents=True)
    b.mkdir()
    rc = _run(
        base, monkeypatch,
        paths=[str(a), str(b)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
    )
    assert rc == 0
    assert (a / _MARKER).is_file()
    assert (b / _MARKER).is_file()


def test_fix_yes_skips_prompt(tmp_path, monkeypatch):
    base = tmp_path / "base"
    proj = base / "proj"
    proj.mkdir(parents=True)

    def _no_prompt(_q, _d):
        raise AssertionError("prompt should not run with --yes")

    def _no_confirm():
        raise AssertionError("confirm should not run with --yes")

    monkeypatch.setenv("HOMEBASE_FIX_TEST_BASE", str(base))
    deps = _stub_deps(prompt_yes_no=_no_prompt, confirm=_no_confirm)
    rc = commands_workspace.cmd_fix(
        paths=[str(proj)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
        **deps,
    )
    assert rc == 0
    assert (proj / _MARKER).is_file()


def test_fix_no_marker_skips_marker_fixer(tmp_path, monkeypatch, capsys):
    base = tmp_path / "base"
    proj = base / "proj"
    proj.mkdir(parents=True)
    rc = _run(
        base, monkeypatch,
        paths=[str(proj)],
        include={commands_workspace.FIX_ARCHIVE_ENTRY},
        yes=True,
    )
    assert rc == 0
    assert not (proj / _MARKER).exists()
    assert "skipped" in capsys.readouterr().out


def test_fix_skips_reserved_underscore_dir(tmp_path, monkeypatch, capsys):
    base = tmp_path / "base"
    tags = base / "_tags"
    tags.mkdir(parents=True)
    rc = _run(
        base, monkeypatch,
        paths=[str(tags)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
    )
    assert rc == 0
    assert "reserved" in capsys.readouterr().out
    assert not (tags / _MARKER).exists()


def test_fix_skips_year_dir(tmp_path, monkeypatch, capsys):
    base = tmp_path / "base"
    year = base / "_archive" / "2024"
    year.mkdir(parents=True)
    rc = _run(
        base, monkeypatch,
        paths=[str(year)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
    )
    assert rc == 0
    assert "year directory" in capsys.readouterr().out


def test_fix_inside_year_dir_renames_when_needed(tmp_path, monkeypatch):
    """User's case: cd _archive/2026; b fix b-rs — must work."""
    base = tmp_path / "base"
    year = base / "_archive" / "2026"
    entry = year / "b-rs"
    entry.mkdir(parents=True)
    f = entry / "main.rs"
    f.write_text("fn main(){}")
    ts = int(datetime(2026, 3, 12, tzinfo=_TZ).timestamp())
    import os
    os.utime(f, (ts, ts))

    rc = _run(
        base, monkeypatch,
        paths=[str(entry)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
    )
    assert rc == 0
    expected = base / "_archive" / "2026" / "2026-03-12_b-rs"
    assert expected.is_dir()
    assert not entry.exists()


def test_fix_inside_year_dir_with_wrong_year_moves(tmp_path, monkeypatch):
    """Entry name's year doesn't match parent year dir → relocate."""
    base = tmp_path / "base"
    parent = base / "_archive" / "2024"
    entry = parent / "2023-08-01_strayed"
    entry.mkdir(parents=True)
    rc = _run(
        base, monkeypatch,
        paths=[str(entry)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
    )
    assert rc == 0
    expected = base / "_archive" / "2023" / "2023-08-01_strayed"
    assert expected.is_dir()
    assert not entry.exists()


def test_fix_skips_subdir_of_archive_entry(tmp_path, monkeypatch, capsys):
    """Anything deeper than _archive/<year>/<entry> must be ignored."""
    base = tmp_path / "base"
    entry = base / "_archive" / "2024" / "2024-01-01_proj"
    deep = entry / "src" / "lib"
    deep.mkdir(parents=True)
    rc = _run(
        base, monkeypatch,
        paths=[str(deep)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
    )
    assert rc == 0
    assert "not a fixable archive target" in capsys.readouterr().err


def test_fix_skips_subdir_inside_project(tmp_path, monkeypatch, capsys):
    """`b fix base/proj/sub` is not a recognized target — skip."""
    base = tmp_path / "base"
    proj_sub = base / "myproj" / "sub"
    proj_sub.mkdir(parents=True)
    rc = _run(
        base, monkeypatch,
        paths=[str(proj_sub)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
    )
    assert rc == 0
    assert "not a direct base entry" in capsys.readouterr().err
    assert not (proj_sub / _MARKER).exists()


def test_fix_archive_entry_renames_and_moves(tmp_path, monkeypatch):
    base = tmp_path / "base"
    src = base / "_archive" / "myproj"
    src.mkdir(parents=True)
    # mtime fallback: write a file with known mtime
    f = src / "note.txt"
    f.write_text("data")
    ts = int(datetime(2023, 6, 15, tzinfo=_TZ).timestamp())
    import os
    os.utime(f, (ts, ts))

    rc = _run(
        base, monkeypatch,
        paths=[str(src)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
    )
    assert rc == 0
    expected = base / "_archive" / "2023" / "2023-06-15_myproj"
    assert expected.is_dir()
    assert (expected / "note.txt").is_file()
    assert not src.exists()


def test_fix_archive_entry_with_canonical_name(tmp_path, monkeypatch):
    base = tmp_path / "base"
    src = base / "_archive" / "2024-03-15_old"
    src.mkdir(parents=True)
    rc = _run(
        base, monkeypatch,
        paths=[str(src)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
    )
    assert rc == 0
    expected = base / "_archive" / "2024" / "2024-03-15_old"
    assert expected.is_dir()
    assert not src.exists()


def test_fix_archive_entry_already_canonical(tmp_path, monkeypatch, capsys):
    base = tmp_path / "base"
    canonical = base / "_archive" / "2024" / "2024-03-15_kept"
    canonical.mkdir(parents=True)
    rc = _run(
        base, monkeypatch,
        paths=[str(canonical)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
    )
    assert rc == 0
    assert "already canonical" in capsys.readouterr().out
    assert canonical.is_dir()


def test_fix_archive_root_fans_out(tmp_path, monkeypatch):
    base = tmp_path / "base"
    archive = base / "_archive"
    # Already-canonical entry in 2024 — should be skipped silently by
    # the fan-out (not even visited).
    canonical = archive / "2024" / "2024-05-01_keepme"
    canonical.mkdir(parents=True)
    # Malformed entry directly under _archive (legacy layout).
    legacy = archive / "needs-fix"
    legacy.mkdir()
    f = legacy / "x.txt"
    f.write_text("x")
    ts = int(datetime(2025, 1, 1, tzinfo=_TZ).timestamp())
    import os
    os.utime(f, (ts, ts))
    # Bad entry sitting inside a year dir (wrong name).
    bad = archive / "2024" / "wrong-name"
    bad.mkdir()
    bf = bad / "note.md"
    bf.write_text("hi")
    bts = int(datetime(2024, 9, 9, tzinfo=_TZ).timestamp())
    os.utime(bf, (bts, bts))

    rc = _run(
        base, monkeypatch,
        paths=[str(archive)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
    )
    assert rc == 0
    moved = base / "_archive" / "2025" / "2025-01-01_needs-fix"
    assert moved.is_dir()
    bad_moved = base / "_archive" / "2024" / "2024-09-09_wrong-name"
    assert bad_moved.is_dir()
    # Canonical sibling untouched
    assert canonical.is_dir()


def test_fix_archive_entry_dest_conflict_returns_error(tmp_path, monkeypatch, capsys):
    base = tmp_path / "base"
    # Pre-existing canonical entry
    (base / "_archive" / "2024" / "2024-03-15_dup").mkdir(parents=True)
    # New malformed entry that would collide
    src = base / "_archive" / "2024-03-15_dup"
    src.mkdir()
    rc = _run(
        base, monkeypatch,
        paths=[str(src)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
    )
    assert rc == 1
    assert "destination exists" in capsys.readouterr().err
    assert src.is_dir()


def test_fix_archive_entry_prompt_for_date(tmp_path, monkeypatch):
    base = tmp_path / "base"
    src = base / "_archive" / "empty"
    src.mkdir(parents=True)
    # No files inside, so mtime walk yields nothing.

    answers = iter(["2022-07-04"])

    def _read(_q):
        return next(answers)

    monkeypatch.setenv("HOMEBASE_FIX_TEST_BASE", str(base))
    # Force interactive mode for the prompt branch.
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    deps = _stub_deps(read_line=_read)
    rc = commands_workspace.cmd_fix(
        paths=[str(src)],
        include=set(commands_workspace.FIX_KINDS),
        yes=False,
        **deps,
    )
    assert rc == 0
    expected = base / "_archive" / "2022" / "2022-07-04_empty"
    assert expected.is_dir()


def test_fix_archive_entry_prompt_rejects_invalid_then_accepts(tmp_path, monkeypatch):
    base = tmp_path / "base"
    src = base / "_archive" / "empty2"
    src.mkdir(parents=True)
    answers = iter(["nope", "2020-13-40", "2020-12-25"])

    def _read(_q):
        return next(answers)

    monkeypatch.setenv("HOMEBASE_FIX_TEST_BASE", str(base))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    deps = _stub_deps(read_line=_read)
    rc = commands_workspace.cmd_fix(
        paths=[str(src)],
        include=set(commands_workspace.FIX_KINDS),
        yes=False,
        **deps,
    )
    assert rc == 0
    expected = base / "_archive" / "2020" / "2020-12-25_empty2"
    assert expected.is_dir()


def test_fix_archive_entry_with_space_separator(tmp_path, monkeypatch):
    """`2026-05-18 mappe` → `2026-05-18_mappe` (rename to underscore form)."""
    base = tmp_path / "base"
    src = base / "_archive" / "2026" / "2026-05-18 mappe"
    src.mkdir(parents=True)
    rc = _run(
        base, monkeypatch,
        paths=[str(src)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
    )
    assert rc == 0
    expected = base / "_archive" / "2026" / "2026-05-18_mappe"
    assert expected.is_dir()
    assert not src.exists()


def test_fix_archive_entry_with_zero_segments(tmp_path, monkeypatch):
    """Legacy `2003-00-00_invisible` → normalized to `2003-01-01_invisible`."""
    base = tmp_path / "base"
    src = base / "_archive" / "2003-00-00_invisible"
    src.mkdir(parents=True)
    rc = _run(
        base, monkeypatch,
        paths=[str(src)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
    )
    assert rc == 0
    expected = base / "_archive" / "2003" / "2003-01-01_invisible"
    assert expected.is_dir()
    assert not src.exists()


def test_fix_archive_tgz_file(tmp_path, monkeypatch):
    """A packed `.tgz` archive at the top of `_archive` gets moved
    into the right year subdir."""
    base = tmp_path / "base"
    arch = base / "_archive"
    arch.mkdir(parents=True)
    tgz = arch / "2009-04-14_old.tgz"
    tgz.write_bytes(b"x")
    rc = _run(
        base, monkeypatch,
        paths=[str(tgz)],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
    )
    assert rc == 0
    expected = base / "_archive" / "2009" / "2009-04-14_old.tgz"
    assert expected.is_file()
    assert not tgz.exists()


def test_fix_all_walks_base_and_archive(tmp_path, monkeypatch):
    base = tmp_path / "base"
    # Active project missing marker
    proj = base / "proj"
    proj.mkdir(parents=True)
    # Hidden + reserved roots shouldn't be touched
    (base / "_tags").mkdir()
    (base / ".homebase").mkdir()
    # Malformed archive entry (space separator)
    bad_arch = base / "_archive" / "2025" / "2025-04-01 stale"
    bad_arch.mkdir(parents=True)

    rc = _run(
        base, monkeypatch,
        paths=[],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
        all_targets=True,
    )
    assert rc == 0
    assert (proj / _MARKER).is_file()
    assert (base / "_archive" / "2025" / "2025-04-01_stale").is_dir()
    assert not (base / "_tags" / _MARKER).exists()
    assert not (base / ".homebase" / _MARKER).exists()


def test_fix_all_with_empty_base_is_noop(tmp_path, monkeypatch):
    base = tmp_path / "base"
    base.mkdir()
    rc = _run(
        base, monkeypatch,
        paths=[],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
        all_targets=True,
    )
    assert rc == 0


def test_fix_all_overrides_explicit_paths(tmp_path, monkeypatch, capsys):
    base = tmp_path / "base"
    proj = base / "proj"
    proj.mkdir(parents=True)
    rc = _run(
        base, monkeypatch,
        paths=["/some/ignored/path"],
        include=set(commands_workspace.FIX_KINDS),
        yes=True,
        all_targets=True,
    )
    assert rc == 0
    err = capsys.readouterr().err
    assert "overrides explicit paths" in err
    assert (proj / _MARKER).is_file()


def test_fix_empty_include_set_errors(tmp_path, monkeypatch, capsys):
    base = tmp_path / "base"
    base.mkdir()
    rc = _run(
        base, monkeypatch,
        paths=[str(base)],
        include=set(),
        yes=True,
    )
    assert rc == 2
    assert "no fixers" in capsys.readouterr().err
