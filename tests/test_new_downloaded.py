from __future__ import annotations

import os
import time
from pathlib import Path

from homebase.cli.parser import build_cli_parser
from homebase.workspace.new import cmd_new


def _run(base: Path, cwd: Path, args: list[str]) -> int:
    ns = build_cli_parser().parse_args(["new", *args])
    return cmd_new(ns, base, cwd)


def _write_config(base: Path, folder: Path) -> None:
    cfg_dir = base / ".homebase"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.yaml").write_text(
        f"new:\n  sources:\n    downloaded:\n      config:\n        folder: {folder}\n"
    )


def test_downloaded_picks_newest_file(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    older = downloads / "older.bin"
    newer = downloads / "report.txt"
    older.write_bytes(b"old")
    time.sleep(0.01)
    newer.write_text("hello")
    os.utime(newer, (time.time() + 5, time.time() + 5))
    _write_config(base, downloads)

    rc = _run(base, tmp_path, ["--downloaded", "--yes", "--no-open"])
    assert rc == 0
    # downloaded source defaults to tmp+timestamp on the folder name.
    candidates = [p for p in base.iterdir() if p.name.endswith("report.tmp")]
    assert len(candidates) == 1
    proj = candidates[0]
    assert (proj / "report.txt").read_text() == "hello"
    assert (proj / ".base.yaml").is_file()
    assert not newer.exists()
    assert older.exists()


def test_downloaded_explicit_name(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "file.bin").write_bytes(b"data")
    _write_config(base, downloads)

    rc = _run(
        base,
        tmp_path,
        ["--downloaded", "myname", "--no-tmp", "--no-timestamp", "--yes", "--no-open"],
    )
    assert rc == 0
    assert (base / "myname" / "file.bin").read_bytes() == b"data"


def test_downloaded_empty_folder_fails(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    _write_config(base, downloads)

    rc = _run(base, tmp_path, ["--downloaded", "--yes", "--no-open"])
    assert rc == 2  # plan() fails because infer_name returns None


def test_downloaded_dry_run(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "file.bin").write_bytes(b"data")
    _write_config(base, downloads)

    rc = _run(base, tmp_path, ["--downloaded", "--dry-run"])
    assert rc == 0
    assert (downloads / "file.bin").exists()
    assert not any(p.is_dir() and not p.name.startswith(".") for p in base.iterdir())


def test_downloaded_skips_hidden_files(tmp_path: Path) -> None:
    """Hidden files (`.DS_Store`, browser partials, etc.) must never
    be chosen — they're metadata, not real downloads."""
    base = tmp_path / "base"
    base.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    # Hidden file is newest in mtime terms, but must be ignored.
    real = downloads / "report.txt"
    real.write_text("real")
    time.sleep(0.01)
    hidden = downloads / ".DS_Store"
    hidden.write_text("junk")
    os.utime(hidden, (time.time() + 100, time.time() + 100))
    _write_config(base, downloads)

    rc = _run(base, tmp_path, ["--downloaded", "--yes", "--no-open"])
    assert rc == 0
    candidates = [p for p in base.iterdir() if p.name.endswith("report.tmp")]
    assert len(candidates) == 1, "real file should have been picked, not .DS_Store"
    assert (candidates[0] / "report.txt").read_text() == "real"
    # The hidden file is left untouched in the downloads folder.
    assert hidden.exists()


def test_downloaded_list_count_config_caps_listing(tmp_path: Path) -> None:
    """The `list_count` config (default 5) limits how many recent files
    are considered/listed. With `--yes` we always pick the single
    newest, but the listing helper itself must honor the cap."""
    from homebase.workspace.new.sources.downloaded import _list_recent_files

    downloads = tmp_path / "downloads"
    downloads.mkdir()
    for i in range(10):
        p = downloads / f"f{i:02d}.bin"
        p.write_bytes(b"x")
        os.utime(p, (1_000_000 + i, 1_000_000 + i))
    listed = _list_recent_files(downloads, 3)
    assert [p.name for p in listed] == ["f09.bin", "f08.bin", "f07.bin"]


def test_downloaded_picker_override_selects_specific_file(tmp_path: Path) -> None:
    """The interactive picker has a test hook: a callable on the class
    that returns the chosen index. We exercise the prepare → infer
    → plan pipeline through it without touching termios / stdin."""
    from homebase.workspace.new.sources.downloaded import DownloadedSource

    base = tmp_path / "base"
    base.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    a = downloads / "first.txt"
    b = downloads / "second.txt"
    c = downloads / "third.txt"
    a.write_text("aaa")
    os.utime(a, (1_000_000, 1_000_000))
    b.write_text("bbb")
    os.utime(b, (2_000_000, 2_000_000))
    c.write_text("ccc")
    os.utime(c, (3_000_000, 3_000_000))
    _write_config(base, downloads)

    # Picker returns index 2 — the OLDEST file (`first.txt`). Index 0
    # would be the newest (`third.txt`).
    DownloadedSource._picker_override = staticmethod(lambda files: 2)
    # The picker only kicks in when `--yes` is NOT passed and stdin /
    # stdout look like TTYs. In pytest stdout is captured so the
    # picker path is skipped — we force-enable by patching the gate.
    # ``--no-confirm`` keeps the picker active (which `--yes` would
    # bypass) while still skipping the post-plan confirm prompt that
    # has nothing to do with the picker.
    import homebase.workspace.new.sources.downloaded as mod
    real_gate = mod._interactive_capable
    mod._interactive_capable = lambda: True
    try:
        rc = _run(base, tmp_path, ["--downloaded", "--no-open", "--no-confirm"])
    finally:
        DownloadedSource._picker_override = None
        mod._interactive_capable = real_gate
    assert rc == 0
    # The oldest file (first.txt) should have been moved — that's
    # what the picker chose, not the newest.
    assert not a.exists()
    assert b.exists()
    assert c.exists()


# ---- helper unit tests -----------------------------------------------


def test_format_age_seconds_under_minute() -> None:
    from homebase.workspace.new.sources.downloaded import _format_age

    assert _format_age(mtime=100.0, now=140.0) == "40s ago"


def test_format_age_minutes_under_hour() -> None:
    from homebase.workspace.new.sources.downloaded import _format_age

    assert _format_age(mtime=0.0, now=125.0) == "2m ago"
    assert _format_age(mtime=0.0, now=3599.0) == "59m ago"


def test_format_age_hours_under_day() -> None:
    from homebase.workspace.new.sources.downloaded import _format_age

    assert _format_age(mtime=0.0, now=3600.0) == "1h ago"
    assert _format_age(mtime=0.0, now=86399.0) == "23h ago"


def test_format_age_days() -> None:
    from homebase.workspace.new.sources.downloaded import _format_age

    assert _format_age(mtime=0.0, now=86400.0) == "1d ago"
    assert _format_age(mtime=0.0, now=259200.0) == "3d ago"


def test_format_age_clamps_negative_delta() -> None:
    """Clock skew or a future mtime must never produce a negative age."""
    from homebase.workspace.new.sources.downloaded import _format_age

    assert _format_age(mtime=200.0, now=100.0) == "0s ago"


def test_format_size_bytes() -> None:
    from homebase.workspace.new.sources.downloaded import _format_size

    assert _format_size(0) == "0 B"
    assert _format_size(512) == "512 B"
    assert _format_size(1023) == "1023 B"


def test_format_size_kilobytes() -> None:
    from homebase.workspace.new.sources.downloaded import _format_size

    assert _format_size(1024) == "1.0 KB"
    assert _format_size(2560) == "2.5 KB"


def test_format_size_megabytes_and_gigabytes() -> None:
    from homebase.workspace.new.sources.downloaded import _format_size

    assert _format_size(1024 * 1024) == "1.0 MB"
    assert _format_size(int(1024 * 1024 * 1.5)) == "1.5 MB"
    assert _format_size(1024 * 1024 * 1024) == "1.0 GB"


def test_format_size_terabytes_for_huge_values() -> None:
    from homebase.workspace.new.sources.downloaded import _format_size

    assert _format_size(1024**4) == "1.0 TB"
    assert _format_size(1024**4 * 5) == "5.0 TB"


def test_where_from_returns_none_off_darwin(monkeypatch) -> None:
    import homebase.workspace.new.sources.downloaded as mod

    monkeypatch.setattr(mod.sys, "platform", "linux")
    assert mod._where_from(Path("/tmp/x")) is None


def test_where_from_returns_none_when_mdls_missing(monkeypatch) -> None:
    import homebase.workspace.new.sources.downloaded as mod

    monkeypatch.setattr(mod.sys, "platform", "darwin")
    monkeypatch.setattr(mod.shutil, "which", lambda _binary: None)
    assert mod._where_from(Path("/tmp/x")) is None


def _run_stub(stdout: str, returncode: int = 0):
    class _Proc:
        def __init__(self) -> None:
            self.stdout = stdout
            self.returncode = returncode
    return lambda *args, **kwargs: _Proc()


def test_where_from_parses_first_quoted_url(monkeypatch) -> None:
    import homebase.workspace.new.sources.downloaded as mod

    monkeypatch.setattr(mod.sys, "platform", "darwin")
    monkeypatch.setattr(mod.shutil, "which", lambda _binary: "/usr/bin/mdls")
    mdls_out = (
        "(\n"
        '    "https://example.com/x",\n'
        '    "https://referrer"\n'
        ")\n"
    )
    monkeypatch.setattr(mod.subprocess, "run", _run_stub(mdls_out))
    assert mod._where_from(Path("/tmp/x")) == "https://example.com/x"


def test_where_from_returns_none_on_null(monkeypatch) -> None:
    import homebase.workspace.new.sources.downloaded as mod

    monkeypatch.setattr(mod.sys, "platform", "darwin")
    monkeypatch.setattr(mod.shutil, "which", lambda _binary: "/usr/bin/mdls")
    monkeypatch.setattr(mod.subprocess, "run", _run_stub("(null)\n"))
    assert mod._where_from(Path("/tmp/x")) is None


def test_where_from_returns_none_when_subprocess_raises(monkeypatch) -> None:
    import homebase.workspace.new.sources.downloaded as mod

    monkeypatch.setattr(mod.sys, "platform", "darwin")
    monkeypatch.setattr(mod.shutil, "which", lambda _binary: "/usr/bin/mdls")

    def _boom(*_args, **_kwargs):
        raise OSError("mdls crashed")

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    assert mod._where_from(Path("/tmp/x")) is None


def test_read_key_returns_digit(monkeypatch) -> None:
    import homebase.workspace.new.sources.downloaded as mod

    chars = iter("5")
    monkeypatch.setattr(mod.sys.stdin, "read", lambda _n=1: next(chars, ""))
    assert mod._read_key() == "5"


def test_read_key_returns_enter_for_cr_and_lf(monkeypatch) -> None:
    import homebase.workspace.new.sources.downloaded as mod

    for ch in ("\r", "\n"):
        monkeypatch.setattr(mod.sys.stdin, "read", lambda _n=1, c=ch: c)
        assert mod._read_key() == "enter"


def test_read_key_returns_arrows(monkeypatch) -> None:
    import homebase.workspace.new.sources.downloaded as mod

    for code, expected in (("A", "up"), ("B", "down")):
        seq = iter(["\x1b", "[", code])
        monkeypatch.setattr(mod.sys.stdin, "read", lambda _n=1, it=seq: next(it, ""))
        assert mod._read_key() == expected


def test_read_key_returns_esc_for_bare_escape(monkeypatch) -> None:
    import homebase.workspace.new.sources.downloaded as mod

    seq = iter(["\x1b", "x"])
    monkeypatch.setattr(mod.sys.stdin, "read", lambda _n=1, it=seq: next(it, ""))
    assert mod._read_key() == "esc"


def test_read_key_returns_empty_for_unhandled_escape_sequence(monkeypatch) -> None:
    import homebase.workspace.new.sources.downloaded as mod

    # ESC '[' followed by an unhandled code (e.g. left arrow 'D').
    seq = iter(["\x1b", "[", "D"])
    monkeypatch.setattr(mod.sys.stdin, "read", lambda _n=1, it=seq: next(it, ""))
    assert mod._read_key() == ""


def test_read_key_returns_empty_for_other_chars(monkeypatch) -> None:
    import homebase.workspace.new.sources.downloaded as mod

    monkeypatch.setattr(mod.sys.stdin, "read", lambda _n=1: "q")
    assert mod._read_key() == ""


def test_render_picker_writes_all_filenames_and_caret(
    capsys, tmp_path: Path
) -> None:
    import homebase.workspace.new.sources.downloaded as mod

    a = tmp_path / "alpha.txt"
    b = tmp_path / "beta.bin"
    a.write_text("a")
    b.write_text("b")
    mod._render_picker([a, b], selected=1)
    out = capsys.readouterr().out
    assert "alpha.txt" in out
    assert "beta.bin" in out
    # The selected entry (index 1) gets the caret prefix.
    assert ">" in out
    assert "modified:" in out
    assert "size:" in out
    assert "from:" in out


def test_render_picker_handles_stat_failure(
    capsys, tmp_path: Path, monkeypatch
) -> None:
    """Files that vanish between listing and rendering must not crash
    the picker — stat failures fall back to zero size + epoch age."""
    import homebase.workspace.new.sources.downloaded as mod

    ghost = tmp_path / "ghost.bin"
    monkeypatch.setattr(mod, "_where_from", lambda _p: None)
    mod._render_picker([ghost], selected=0)
    out = capsys.readouterr().out
    assert "ghost.bin" in out
    assert "0 B" in out


def test_interactive_choose_with_picker_override(tmp_path: Path) -> None:
    """``picker_override`` lets tests pick by index without touching
    termios. A valid index returns the selected file."""
    from homebase.workspace.new.sources.downloaded import _interactive_choose

    files = [tmp_path / "a", tmp_path / "b", tmp_path / "c"]
    chosen = _interactive_choose(files, picker_override=lambda _fs: 2)
    assert chosen == files[2]


def test_interactive_choose_picker_override_out_of_range_returns_none(
    tmp_path: Path,
) -> None:
    from homebase.workspace.new.sources.downloaded import _interactive_choose

    files = [tmp_path / "a", tmp_path / "b"]
    assert _interactive_choose(files, picker_override=lambda _fs: 99) is None


def test_interactive_choose_picker_override_non_int_returns_none(
    tmp_path: Path,
) -> None:
    from homebase.workspace.new.sources.downloaded import _interactive_choose

    files = [tmp_path / "a"]
    assert _interactive_choose(
        files, picker_override=lambda _fs: "not-an-int"
    ) is None


def test_interactive_choose_empty_file_list_returns_none() -> None:
    from homebase.workspace.new.sources.downloaded import _interactive_choose

    assert _interactive_choose([]) is None


def test_interactive_capable_false_when_stdin_not_tty(monkeypatch) -> None:
    import homebase.workspace.new.sources.downloaded as mod

    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(mod.sys.stdout, "isatty", lambda: True)
    assert mod._interactive_capable() is False


def test_interactive_capable_false_when_stdout_not_tty(monkeypatch) -> None:
    import homebase.workspace.new.sources.downloaded as mod

    monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(mod.sys.stdout, "isatty", lambda: False)
    assert mod._interactive_capable() is False


def test_interactive_capable_handles_oserror(monkeypatch) -> None:
    import homebase.workspace.new.sources.downloaded as mod

    def _boom() -> bool:
        raise OSError("detached")

    monkeypatch.setattr(mod.sys.stdin, "isatty", _boom)
    assert mod._interactive_capable() is False


def test_downloaded_recent_raises_when_folder_missing(tmp_path: Path) -> None:
    """``_recent()`` raises when the configured folder doesn't exist."""
    from homebase.workspace.new.base import NewContext, Source
    from homebase.workspace.new.sources.downloaded import DownloadedSource

    src = DownloadedSource(
        config={"folder": str(tmp_path / "missing"), "list_count": 5},
    )
    assert isinstance(src, Source)
    ctx = NewContext(base_dir=tmp_path, cwd=tmp_path)
    assert ctx is not None
    try:
        src._recent()
    except ValueError as exc:
        assert "downloads folder not found" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_downloaded_recent_raises_when_folder_empty(tmp_path: Path) -> None:
    from homebase.workspace.new.sources.downloaded import DownloadedSource

    downloads = tmp_path / "downloads"
    downloads.mkdir()
    src = DownloadedSource(
        config={"folder": str(downloads), "list_count": 5},
    )
    try:
        src._recent()
    except ValueError as exc:
        assert "no files in downloads folder" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_downloaded_list_count_invalid_falls_back_to_default(tmp_path: Path) -> None:
    """A non-int ``list_count`` config must not blow up — fall back
    to the default. Default is 5 (``_DEFAULT_LIST_COUNT``)."""
    from homebase.workspace.new.sources.downloaded import (
        _DEFAULT_LIST_COUNT,
        DownloadedSource,
    )

    src = DownloadedSource(
        config={"folder": str(tmp_path), "list_count": "abc"},
    )
    assert src._list_count() == _DEFAULT_LIST_COUNT


def test_downloaded_list_count_floor_at_one(tmp_path: Path) -> None:
    from homebase.workspace.new.sources.downloaded import DownloadedSource

    src = DownloadedSource(
        config={"folder": str(tmp_path), "list_count": 0},
    )
    assert src._list_count() == 1


def test_downloaded_detects_always_false(tmp_path: Path) -> None:
    """``detects`` must never auto-trigger; only --downloaded selects it."""
    from homebase.workspace.new.base import NewContext
    from homebase.workspace.new.sources.downloaded import DownloadedSource

    src = DownloadedSource(config={})
    ctx = NewContext(base_dir=tmp_path, cwd=tmp_path)
    assert src.detects("anything", ctx) is False
    assert src.detects("", ctx) is False
