from __future__ import annotations

from pathlib import Path

from homebase.cli.parser import build_cli_parser
from homebase.workspace.new import cmd_new


def _run(base: Path, cwd: Path, args: list[str]) -> int:
    ns = build_cli_parser().parse_args(["new", *args])
    return cmd_new(ns, base, cwd)


def test_local_moves_directory(tmp_path: Path) -> None:
    src = tmp_path / "work" / "old-thing"
    src.mkdir(parents=True)
    (src / "file.txt").write_text("hi")
    base = tmp_path / "base"
    base.mkdir()

    rc = _run(base, tmp_path / "work", [str(src)])
    assert rc == 0
    target = base / "old-thing"
    assert target.is_dir()
    assert (target / "file.txt").read_text() == "hi"
    assert (target / ".base.yaml").is_file()
    assert not src.exists()


def test_local_with_explicit_name(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    base = tmp_path / "base"
    base.mkdir()

    rc = _run(base, tmp_path, [str(src), "myproj"])
    assert rc == 0
    assert (base / "myproj").is_dir()
    assert not (base / "src").exists()


def test_local_refuses_when_source_under_base(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    src = base / "already-here"
    src.mkdir()

    rc = _run(base, tmp_path, [str(src)])
    assert rc == 1
    assert src.exists()


def test_local_missing_source_fails(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    rc = _run(base, tmp_path, [str(tmp_path / "nope")])
    assert rc == 1


def test_local_conflict_fails(tmp_path: Path) -> None:
    src = tmp_path / "thing"
    src.mkdir()
    base = tmp_path / "base"
    base.mkdir()
    (base / "thing").mkdir()

    rc = _run(base, tmp_path, [str(src)])
    assert rc == 1
    assert src.exists()


def test_local_dry_run_no_writes(tmp_path: Path) -> None:
    src = tmp_path / "thing"
    src.mkdir()
    base = tmp_path / "base"
    base.mkdir()

    rc = _run(base, tmp_path, [str(src), "--dry-run"])
    assert rc == 0
    assert src.exists()
    assert not (base / "thing").exists()


def test_local_with_tmp_suffix(tmp_path: Path) -> None:
    src = tmp_path / "thing"
    src.mkdir()
    base = tmp_path / "base"
    base.mkdir()

    rc = _run(base, tmp_path, [str(src), "--tmp"])
    assert rc == 0
    assert (base / "thing.tmp").is_dir()
    assert not src.exists()


def test_local_relative_dotslash(tmp_path: Path) -> None:
    src = tmp_path / "rel"
    src.mkdir()
    base = tmp_path / "base"
    base.mkdir()

    ns = build_cli_parser().parse_args(["new", "./rel"])
    rc = cmd_new(ns, base, tmp_path)
    assert rc == 0
    assert (base / "rel").is_dir()
