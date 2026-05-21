from __future__ import annotations

from pathlib import Path

from homebase.cli.parser import build_cli_parser
from homebase.workspace.new import cmd_new


def _run(base: Path, cwd: Path, args: list[str]) -> int:
    ns = build_cli_parser().parse_args(["new", *args])
    return cmd_new(ns, base, cwd)


def test_multi_creates_n_empty_projects(tmp_path: Path) -> None:
    rc = _run(tmp_path, tmp_path, ["--multi", "a", "b", "c"])
    assert rc == 0
    assert (tmp_path / "a").is_dir()
    assert (tmp_path / "b").is_dir()
    assert (tmp_path / "c").is_dir()


def test_multi_mixed_sources_autodetect(tmp_path: Path) -> None:
    src = tmp_path / "work" / "old"
    src.mkdir(parents=True)
    base = tmp_path / "base"
    base.mkdir()

    rc = _run(
        base,
        tmp_path,
        ["--multi", str(src), "bare-name"],
    )
    assert rc == 0
    # path → moved; bare → empty
    assert (base / "old").is_dir()
    assert (base / "bare-name").is_dir()
    assert not src.exists()


def test_multi_continues_on_per_item_failure(tmp_path: Path) -> None:
    existing = tmp_path / "exists"
    existing.mkdir()
    rc = _run(tmp_path, tmp_path, ["--multi", "fresh", "exists", "alsofresh"])
    # First and third succeed; "exists" collides → rc != 0 but
    # remaining items still processed.
    assert rc != 0
    assert (tmp_path / "fresh").is_dir()
    assert (tmp_path / "alsofresh").is_dir()


def test_multi_with_mode_flag_forces_all(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    rc = _run(base, tmp_path, ["--multi", "--empty", "ok", "sub/leaf"])
    assert rc == 0
    assert (base / "ok").is_dir()
    assert (base / "leaf").is_dir()
    assert not (base / "sub").exists()


def test_multi_dry_run_writes_nothing(tmp_path: Path) -> None:
    rc = _run(tmp_path, tmp_path, ["--multi", "a", "b", "--dry-run"])
    assert rc == 0
    assert not (tmp_path / "a").exists()
    assert not (tmp_path / "b").exists()
