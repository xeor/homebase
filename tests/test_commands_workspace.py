from __future__ import annotations

from pathlib import Path

from homebase.commands import workspace as commands_workspace


def test_cmd_archive_ls_no_archives(capsys, tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    src = base / "proj"
    src.mkdir()
    rc = commands_workspace.cmd_archive_ls(
        base,
        str(src),
        policy_reason_outside_base=lambda _p, _b: None,
        archive_root=lambda b: b / "_archive",
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "no archives found" in out


def test_suggest_project_root_single_chain(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b"
    path.mkdir(parents=True)
    out = commands_workspace.suggest_project_root(tmp_path)
    assert out == path
