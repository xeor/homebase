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
