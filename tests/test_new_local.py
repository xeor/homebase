from __future__ import annotations

from pathlib import Path

import homebase.tmux.flow as tmux_flow
from homebase.cli.parser import build_cli_parser
from homebase.workspace.new import cmd_new
from homebase.workspace.new.sources import local as local_source


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


def test_local_autodetect_nonexistent_path_like_input_creates_empty(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()

    ns = build_cli_parser().parse_args(["new", "testing/"])
    rc = cmd_new(ns, base, tmp_path)
    assert rc == 0
    assert (base / "testing").is_dir()


def test_local_explicit_flag_keeps_missing_path_error(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()

    ns = build_cli_parser().parse_args(["new", "testing/", "--local"])
    rc = cmd_new(ns, base, tmp_path)
    assert rc == 1
    assert not (base / "testing").exists()


def test_auto_source_sentinel_is_ignored(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()

    ns = build_cli_parser().parse_args(["new", "testing/"])
    ns.child_key = "auto"
    rc = cmd_new(ns, base, tmp_path)
    assert rc == 0
    assert (base / "testing").is_dir()


def test_local_relative_dot_imports_cwd(tmp_path: Path) -> None:
    src = tmp_path / "work" / "dotproj"
    src.mkdir(parents=True)
    (src / "file.txt").write_text("hi")
    base = tmp_path / "base"
    base.mkdir()

    ns = build_cli_parser().parse_args(["new", "."])
    rc = cmd_new(ns, base, src)
    assert rc == 0
    target = base / "dotproj"
    assert target.is_dir()
    assert (target / "file.txt").read_text() == "hi"
    assert not src.exists()


def test_local_move_from_inside_source_skips_open_shell(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "work" / "proj"
    (src / "sub").mkdir(parents=True)
    base = tmp_path / "base"
    base.mkdir()

    called = {"open": 0}

    def _open_shell_in_dir(_path: Path) -> int:
        called["open"] += 1
        return 0

    monkeypatch.setattr(tmux_flow, "open_shell_in_dir", _open_shell_in_dir)
    ns = build_cli_parser().parse_args(["new", ".."])  # move `proj` while cwd is `proj/sub`
    rc = cmd_new(ns, base, src / "sub")
    assert rc == 0
    assert called["open"] == 0
    assert (base / "proj").is_dir()


def test_local_move_from_inside_source_emits_cd_warning(tmp_path: Path, capsys) -> None:
    src = tmp_path / "work" / "proj"
    src.mkdir(parents=True)
    base = tmp_path / "base"
    base.mkdir()

    ns = build_cli_parser().parse_args(["new", ".", "--no-open"])
    rc = cmd_new(ns, base, src)
    assert rc == 0
    err = capsys.readouterr().err
    assert "moved current working directory" in err
    assert f"cd {base / 'proj'}" in err


def test_local_move_from_inside_source_writes_wrapper_cd_handoff(
    tmp_path: Path,
    monkeypatch,
) -> None:
    src = tmp_path / "work" / "proj"
    src.mkdir(parents=True)
    base = tmp_path / "base"
    base.mkdir()
    cd_file = tmp_path / "cd-handoff.txt"
    cd_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("HOMEBASE_CD_FILE", str(cd_file))

    ns = build_cli_parser().parse_args(["new", "."])
    rc = cmd_new(ns, base, src)
    assert rc == 0
    assert cd_file.read_text(encoding="utf-8").strip() == str((base / "proj").resolve())


def test_local_move_from_nested_cwd_writes_nested_wrapper_cd_handoff(
    tmp_path: Path,
    monkeypatch,
) -> None:
    src = tmp_path / "work" / "proj"
    nested = src / "a" / "b"
    nested.mkdir(parents=True)
    base = tmp_path / "base"
    base.mkdir()
    cd_file = tmp_path / "cd-handoff.txt"
    cd_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("HOMEBASE_CD_FILE", str(cd_file))

    ns = build_cli_parser().parse_args(["new", "../.."])
    rc = cmd_new(ns, base, nested)
    assert rc == 0
    assert cd_file.read_text(encoding="utf-8").strip() == str((base / "proj" / "a" / "b").resolve())


def test_local_move_with_wrapper_handoff_suppresses_cd_warning(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    src = tmp_path / "work" / "proj"
    nested = src / "a"
    nested.mkdir(parents=True)
    base = tmp_path / "base"
    base.mkdir()
    cd_file = tmp_path / "cd-handoff.txt"
    cd_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("HOMEBASE_CD_FILE", str(cd_file))

    ns = build_cli_parser().parse_args(["new", ".."])
    rc = cmd_new(ns, base, nested)
    assert rc == 0
    err = capsys.readouterr().err
    assert "moved current working directory" not in err


def test_homebase_debug_emits_new_pipeline_logs(tmp_path: Path, monkeypatch, capsys) -> None:
    base = tmp_path / "base"
    base.mkdir()
    monkeypatch.setenv("HOMEBASE_DEBUG", "1")

    ns = build_cli_parser().parse_args(["new", "proj", "--dry-run"])
    rc = cmd_new(ns, base, tmp_path)
    assert rc == 0
    err = capsys.readouterr().err
    assert "[debug] new: start" in err
    assert "[debug] new: plan done" in err


def test_local_with_git_wraps_under_repo_non_interactive(tmp_path: Path) -> None:
    src = tmp_path / "work" / "thing"
    (src / ".git").mkdir(parents=True)
    (src / "file.txt").write_text("hi")
    base = tmp_path / "base"
    base.mkdir()

    rc = _run(base, tmp_path, [str(src)])
    assert rc == 0
    target = base / "thing"
    assert target.is_dir()
    assert (target / ".base.yaml").is_file()
    assert (target / "repo" / ".git").is_dir()
    assert (target / "repo" / "file.txt").read_text() == "hi"
    assert not src.exists()


def test_local_with_git_interactive_no_keeps_as_is(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "work" / "thing"
    (src / ".git").mkdir(parents=True)
    (src / "file.txt").write_text("hi")
    base = tmp_path / "base"
    base.mkdir()

    monkeypatch.setattr(local_source.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(local_source, "confirm", lambda *a, **kw: False)

    rc = _run(base, tmp_path, [str(src)])
    assert rc == 0
    target = base / "thing"
    assert (target / "file.txt").read_text() == "hi"
    assert (target / ".git").is_dir()
    assert not (target / "repo").exists()


def test_local_with_git_yes_flag_wraps_without_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    src = tmp_path / "work" / "thing"
    (src / ".git").mkdir(parents=True)
    base = tmp_path / "base"
    base.mkdir()

    def _no_prompt(*_a, **_kw) -> bool:
        raise AssertionError("confirm should not be called when --yes is set")

    monkeypatch.setattr(local_source.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(local_source, "confirm", _no_prompt)

    rc = _run(base, tmp_path, [str(src), "--yes"])
    assert rc == 0
    assert (base / "thing" / "repo" / ".git").is_dir()


def test_local_with_git_dry_run_shows_repo_step(
    tmp_path: Path,
    capsys,
) -> None:
    src = tmp_path / "work" / "thing"
    (src / ".git").mkdir(parents=True)
    base = tmp_path / "base"
    base.mkdir()

    rc = _run(base, tmp_path, [str(src), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "mkdir" in out
    assert f"-> {base / 'thing' / 'repo'}" in out
    assert src.exists()


def test_local_with_git_wrapper_handoff_lands_in_repo(
    tmp_path: Path,
    monkeypatch,
) -> None:
    src = tmp_path / "work" / "proj"
    nested = src / "a" / "b"
    nested.mkdir(parents=True)
    (src / ".git").mkdir()
    base = tmp_path / "base"
    base.mkdir()
    cd_file = tmp_path / "cd-handoff.txt"
    cd_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("HOMEBASE_CD_FILE", str(cd_file))

    ns = build_cli_parser().parse_args(["new", "../.."])
    rc = cmd_new(ns, base, nested)
    assert rc == 0
    expected = (base / "proj" / "repo" / "a" / "b").resolve()
    assert cd_file.read_text(encoding="utf-8").strip() == str(expected)


def test_local_move_does_not_run_tag_symlink_sync(tmp_path: Path, monkeypatch) -> None:
    src = tmp_path / "work" / "nosync"
    src.mkdir(parents=True)
    base = tmp_path / "base"
    base.mkdir()

    def _boom(_base_dir: Path) -> str | None:
        raise AssertionError("sync_tag_symlinks should not run during b new local move")

    monkeypatch.setattr(local_source, "sync_tag_symlinks", _boom, raising=False)
    ns = build_cli_parser().parse_args(["new", str(src)])
    rc = cmd_new(ns, base, tmp_path)
    assert rc == 0
    assert (base / "nosync").is_dir()
