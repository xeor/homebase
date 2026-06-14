from __future__ import annotations

from pathlib import Path

import pytest

from homebase.commands import workspace as commands_workspace
from homebase.core.models import PreOutcome


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


def test_cmd_rm_prompts_and_aborts(monkeypatch, tmp_path: Path) -> None:
    """Without ``--force`` the user must say yes; a "no" answer
    aborts and the target is left intact."""
    base = tmp_path / "base"
    base.mkdir()
    proj = base / "proj"
    proj.mkdir()
    monkeypatch.setenv("HB_BASE", str(base))
    deleted: list[Path] = []
    rc = commands_workspace.cmd_rm(
        str(proj),
        env_base_dir_key="HB_BASE",
        policy_reason_outside_base=lambda _t, _b: None,
        prompt_yes_no=lambda _q, _default: False,  # user typed "n"
        delete_internal=lambda _b, t: deleted.append(t),
        force_outside_base=False,
        force=False,
    )
    assert rc == 1
    assert deleted == []
    assert proj.is_dir()


def test_cmd_rm_force_skips_prompt(monkeypatch, tmp_path: Path) -> None:
    """``--force`` skips the y/N prompt and goes straight to delete."""
    base = tmp_path / "base"
    base.mkdir()
    proj = base / "proj"
    proj.mkdir()
    monkeypatch.setenv("HB_BASE", str(base))
    deleted: list[Path] = []
    rc = commands_workspace.cmd_rm(
        str(proj),
        env_base_dir_key="HB_BASE",
        policy_reason_outside_base=lambda _t, _b: None,
        # Will explode if called — proving --force really skipped it.
        prompt_yes_no=lambda *_a, **_kw: pytest.fail("prompt should be skipped"),
        delete_internal=lambda _b, t: deleted.append(t),
        force_outside_base=False,
        force=True,
    )
    assert rc == 0
    assert deleted == [proj.resolve()]


def test_cmd_rm_prompt_yes_proceeds(monkeypatch, tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    proj = base / "proj"
    proj.mkdir()
    monkeypatch.setenv("HB_BASE", str(base))
    deleted: list[Path] = []
    rc = commands_workspace.cmd_rm(
        str(proj),
        env_base_dir_key="HB_BASE",
        policy_reason_outside_base=lambda _t, _b: None,
        prompt_yes_no=lambda _q, _default: True,  # user typed "y"
        delete_internal=lambda _b, t: deleted.append(t),
        force_outside_base=False,
        force=False,
    )
    assert rc == 0
    assert deleted == [proj.resolve()]


def test_cmd_cd_spawns_shell_in_project(tmp_path: Path) -> None:
    """``b cd foo`` calls ``open_shell_in_dir`` with the resolved
    base/foo path."""
    from homebase.commands.basic import cmd_cd

    (tmp_path / "foo").mkdir()
    called: list[Path] = []
    rc = cmd_cd(
        tmp_path,
        "foo",
        archive_dir_name="_archive",
        open_shell_in_dir=lambda p: (called.append(p), 0)[1],
    )
    assert rc == 0
    assert called == [(tmp_path / "foo").resolve()]


def test_cmd_open_uses_open_mode_for_project(tmp_path: Path) -> None:
    from homebase.commands.basic import cmd_open

    (tmp_path / "foo").mkdir()
    called: list[tuple[Path, Path]] = []
    rc = cmd_open(
        tmp_path,
        "foo",
        archive_dir_name="_archive",
        open_with_mode=lambda base, path: (called.append((base, path)), 0)[1],
    )
    assert rc == 0
    assert called == [(tmp_path, (tmp_path / "foo").resolve())]


def test_cmd_cd_empty_name_drops_into_base(tmp_path: Path) -> None:
    from homebase.commands.basic import cmd_cd

    called: list[Path] = []
    rc = cmd_cd(
        tmp_path,
        "",
        archive_dir_name="_archive",
        open_shell_in_dir=lambda p: (called.append(p), 0)[1],
    )
    assert rc == 0
    assert called == [tmp_path]


def test_cmd_cd_refuses_archive(tmp_path: Path) -> None:
    """``b cd _archive`` is blocked — the archive isn't a project."""
    from homebase.commands.basic import cmd_cd

    (tmp_path / "_archive").mkdir()
    rc = cmd_cd(
        tmp_path,
        "_archive",
        archive_dir_name="_archive",
        open_shell_in_dir=lambda _p: pytest.fail("should never spawn"),
    )
    assert rc == 2


def test_cmd_cd_refuses_unknown_project(tmp_path: Path) -> None:
    from homebase.commands.basic import cmd_cd

    rc = cmd_cd(
        tmp_path,
        "no-such-thing",
        archive_dir_name="_archive",
        open_shell_in_dir=lambda _p: pytest.fail("should never spawn"),
    )
    assert rc == 2


def test_cmd_cd_refuses_escape(tmp_path: Path) -> None:
    """``b cd ../foo`` must not escape base."""
    from homebase.commands.basic import cmd_cd

    rc = cmd_cd(
        tmp_path,
        "../outside",
        archive_dir_name="_archive",
        open_shell_in_dir=lambda _p: pytest.fail("should never spawn"),
    )
    assert rc == 2


def test_exec_shell_at_parent_if_cwd_under(monkeypatch, tmp_path: Path) -> None:
    """When the cwd captured BEFORE the destroy was inside the target,
    we exec a shell at target.parent. When the original cwd was
    elsewhere we don't."""
    from homebase.commands import archive as commands_archive

    base = tmp_path / "base"
    base.mkdir()
    proj = base / "proj"
    proj.mkdir()

    landed: list[Path] = []
    monkeypatch.setattr(
        commands_archive,
        "open_shell_in_dir",
        lambda p: landed.append(p),
    )

    # Original cwd was the target → spawns shell at parent.
    commands_archive._exec_shell_at_parent_if_cwd_under(
        proj, base, original_cwd=proj,
    )
    assert landed == [proj.parent]

    # Original cwd was inside a subdir of the target → same.
    landed.clear()
    sub = proj / "sub"
    sub.mkdir()
    commands_archive._exec_shell_at_parent_if_cwd_under(
        proj, base, original_cwd=sub,
    )
    assert landed == [proj.parent]

    # Original cwd was unrelated → no shell.
    landed.clear()
    other = tmp_path / "other"
    other.mkdir()
    commands_archive._exec_shell_at_parent_if_cwd_under(
        proj, base, original_cwd=other,
    )
    assert landed == []


def test_safety_helper_uses_original_cwd_not_current(
    monkeypatch, tmp_path: Path
) -> None:
    """Regression: ``archive_service.delete_internal`` chdir's to base
    before the target is removed. The helper must honor the cwd as it
    was BEFORE that chdir — otherwise it never spawns a recovery
    shell for someone deleting the directory they're standing in."""
    from homebase.commands import archive as commands_archive

    base = tmp_path / "base"
    base.mkdir()
    proj = base / "proj"
    proj.mkdir()

    landed: list[Path] = []
    monkeypatch.setattr(
        commands_archive,
        "open_shell_in_dir",
        lambda p: landed.append(p),
    )
    # Simulate the chdir that the inner code path did.
    monkeypatch.chdir(base)
    # If the helper queried Path.cwd() it would see base and bail.
    # By passing original_cwd=proj we prove it uses what we tell it.
    commands_archive._exec_shell_at_parent_if_cwd_under(
        proj, base, original_cwd=proj,
    )
    assert landed == [base]


def test_exec_shell_falls_back_to_base_when_parent_gone(
    monkeypatch, tmp_path: Path
) -> None:
    """If both target AND its parent have vanished, fall back to base."""
    from homebase.commands import archive as commands_archive

    base = tmp_path / "base"
    base.mkdir()
    landed: list[Path] = []
    monkeypatch.setattr(
        commands_archive,
        "open_shell_in_dir",
        lambda p: landed.append(p),
    )
    fake_target = tmp_path / "nowhere" / "proj"
    fake_cwd = fake_target / "sub"
    commands_archive._exec_shell_at_parent_if_cwd_under(
        fake_target, base, original_cwd=fake_cwd,
    )
    assert landed == [base]


def test_archive_cmd_rm_honors_pre_hook_cancel(monkeypatch, tmp_path: Path) -> None:
    from homebase.commands import archive as commands_archive

    base = tmp_path / "base"
    base.mkdir()
    proj = base / "proj"
    proj.mkdir()
    monkeypatch.setenv("BASE_FOLDER", str(base))

    called = {"workspace_rm": 0}

    monkeypatch.setattr(
        commands_archive,
        "dispatch_pre_cli",
        lambda **_kwargs: PreOutcome(cancelled=True, reason="blocked", change={}),
    )

    def _cmd_rm(*_args, **_kwargs):
        called["workspace_rm"] += 1
        return 0

    monkeypatch.setattr(commands_archive.commands_workspace, "cmd_rm", _cmd_rm)
    rc = commands_archive.cmd_rm(
        str(proj),
        force_outside_base=False,
        force=True,
        hook_specs={("pre", "delete"): [object()]},
    )
    assert rc == 1
    assert called["workspace_rm"] == 0
