from __future__ import annotations

from pathlib import Path

import pytest

from homebase.core import setup_tools as setup_tools


def test_compact_path_for_display_uses_tilde() -> None:
    home = Path.home()
    out = setup_tools.compact_path_for_display(str(home / "x"))
    assert out.startswith("~")


def test_shell_init_target_paths() -> None:
    """The wrapper target is conf.d/ for fish (auto-sourced) and a
    dedicated homebase init file for bash/zsh (sourced from rc)."""
    home = Path.home()
    assert setup_tools._shell_init_target_for_shell("fish") == (
        home / ".config/fish/conf.d/b.fish"
    )
    assert setup_tools._shell_init_target_for_shell("bash") == (
        home / ".local/share/homebase/shell-init.bash"
    )
    assert setup_tools._shell_init_target_for_shell("zsh") == (
        home / ".local/share/homebase/shell-init.zsh"
    )
    assert setup_tools._shell_init_target_for_shell("powershell") is None


def test_shell_init_installed_detects_present_and_missing(
    tmp_path: Path,
) -> None:
    """For fish the conf.d file must match the script byte-for-byte;
    for bash/zsh both the init file AND the source line in rc count."""
    # --- fish path (no rc file involved) ---
    fish_target = tmp_path / "conf.d" / "b.fish"
    fish_target.parent.mkdir(parents=True)
    body = "# script\nfunction b\n  ...\nend\n"
    fish_target.write_text(body)
    assert setup_tools._shell_init_installed("fish", body, fish_target, None)
    fish_target.write_text("stale")
    assert not setup_tools._shell_init_installed("fish", body, fish_target, None)

    # --- bash path (script + rc source line) ---
    bash_target = tmp_path / "share" / "homebase" / "shell-init.bash"
    bash_target.parent.mkdir(parents=True)
    bash_target.write_text(body)
    rc = tmp_path / ".bashrc"
    line = setup_tools._shell_init_source_line("bash", bash_target)
    rc.write_text("# user stuff\n" + line + "\nmore stuff\n")
    assert setup_tools._shell_init_installed("bash", body, bash_target, rc)
    # missing source line → not installed
    rc.write_text("# user stuff only\n")
    assert not setup_tools._shell_init_installed("bash", body, bash_target, rc)


def test_cmd_setup_offers_to_install_shell_init(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """End-to-end through cmd_setup: with no wrapper installed and
    auto-confirm, the script lands at the expected target AND the
    user's rc file gets the source line appended."""
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")
    (base_dir / ".homebase").mkdir()
    (base_dir / ".homebase" / ".gitignore").write_text("cache.sqlite3\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "b").symlink_to((bin_dir / "b").resolve())

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x"
        if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")
    monkeypatch.setenv("SHELL", "/usr/local/bin/bash")

    expected_wrapper = "# wrapper body\nb() { :; }\n"
    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, _d: True,  # yes to every fix
        completion_script_fn=lambda _s: "# completion\n",
        shell_init_script_fn=lambda _s: expected_wrapper,
    )
    assert rc == 0
    init_target = home / ".local/share/homebase/shell-init.bash"
    assert init_target.is_file()
    assert init_target.read_text() == expected_wrapper
    bashrc = home / ".bashrc"
    assert bashrc.is_file()
    assert "homebase shell integration" in bashrc.read_text()


def test_has_any_tmux_save_binding_detects_bind_line() -> None:
    text = 'bind-key t run-shell -b "uv run --script b.py b tmux save"\n'
    assert setup_tools.has_any_tmux_save_binding(text) is True


def test_tmux_save_binding_lines_returns_only_binding_lines() -> None:
    text = "\n".join(
        [
            "# comment",
            'bind-key t run-shell -b "uv run --script b.py b tmux save"',
            'bind-key x run-shell -b "echo hi"',
            'bind t run-shell -b "uv run --script b.py b tmux save"',
        ]
    )
    out = setup_tools.tmux_save_binding_lines(text)
    assert len(out) == 2
    assert all("b tmux save" in line for line in out)


def test_recommended_tmux_save_binding_contains_expected_parts() -> None:
    line = setup_tools.recommended_tmux_save_binding(Path("/tmp/b"), "/usr/bin/uv", "/usr/bin/tmux")
    assert "TMUX_BIN=" in line
    assert "tmux save" in line


def test_state_text_labels() -> None:
    assert setup_tools._state_text("PASS") == "already configured"
    assert setup_tools._state_text("WARN") == "needs change"
    assert setup_tools._state_text("FAIL") == "missing"


def test_write_tmux_binding_appends_when_missing(tmp_path: Path) -> None:
    conf = tmp_path / ".tmux.conf"
    conf.write_text("set -g mouse on\n")
    expected = "bind-key t run-shell -b 'uv run --script /tmp/b tmux save'"
    setup_tools.write_tmux_binding(conf, expected)
    text = conf.read_text()
    assert "set -g mouse on" in text
    assert expected in text


def test_write_tmux_binding_replaces_existing_save_bind(tmp_path: Path) -> None:
    conf = tmp_path / ".tmux.conf"
    conf.write_text(
        "set -g mouse on\n"
        "bind-key t run-shell -b 'old b tmux save command'\n"
        "bind-key x run-shell -b 'echo x'\n"
    )
    expected = "bind-key t run-shell -b 'new b tmux save command'"
    setup_tools.write_tmux_binding(conf, expected)
    lines = conf.read_text().splitlines()
    assert expected in lines
    assert not any("old b tmux save command" in line for line in lines)
    assert any("bind-key x" in line for line in lines)


def test_cmd_setup_return_code_warns_do_not_fail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")
    (base_dir / ".homebase").mkdir()
    (base_dir / ".homebase" / ".gitignore").write_text("cache.sqlite3\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "b").symlink_to((bin_dir / "b").resolve())

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x" if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, _d: False,
    )
    assert rc == 0


def test_cmd_setup_return_code_missing_required_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(setup_tools, "find_executable", lambda _name, extra_candidates=(): None)
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (False, "missing deps"))
    monkeypatch.setenv("PATH", "/usr/bin")

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, _d: False,
    )
    assert rc == 1


def test_write_homebase_gitignore_adds_cache_rule_once(tmp_path: Path) -> None:
    path = tmp_path / ".gitignore"
    setup_tools._write_homebase_gitignore(path)
    setup_tools._write_homebase_gitignore(path)
    lines = path.read_text().splitlines()
    assert lines == ["cache.sqlite3"]


def test_cmd_setup_fixes_wrong_symlink_target(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    old_bin_dir = tmp_path / "oldbin"
    base_dir.mkdir()
    bin_dir.mkdir()
    old_bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")
    (old_bin_dir / "b").write_text("#!/bin/sh\n")
    (base_dir / ".homebase").mkdir()
    (base_dir / ".homebase" / ".gitignore").write_text("cache.sqlite3\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    launcher = local_bin / "b"
    launcher.symlink_to((old_bin_dir / "b").resolve())

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x" if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, _d: True,
    )
    assert rc == 0
    assert launcher.is_symlink()
    assert launcher.resolve() == (bin_dir / "b").resolve()


def test_cmd_setup_renames_plain_launcher_file_before_symlink(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")
    (base_dir / ".homebase").mkdir()
    (base_dir / ".homebase" / ".gitignore").write_text("cache.sqlite3\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    launcher = local_bin / "b"
    launcher.write_text("not a symlink\n")

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x" if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, _d: True,
    )
    assert rc == 0
    assert launcher.is_symlink()
    backups = list(local_bin.glob("b.bak-*"))
    assert len(backups) == 1


def test_cmd_setup_validate_first_fix_order(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x" if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")

    prompts: list[str] = []

    def _prompt(question: str, _default: bool) -> bool:
        prompts.append(question)
        return True

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=_prompt,
    )
    assert rc == 0
    assert prompts[0].startswith("create ")
    assert "ensure launcher symlink" in prompts[1]
    assert "ensure" in prompts[2] and ".gitignore" in prompts[2]
    assert "apply recommended tmux binding" in prompts[-1]


def test_cmd_setup_missing_config_is_warning_not_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")
    (base_dir / ".homebase").mkdir()
    (base_dir / ".homebase" / ".gitignore").write_text("cache.sqlite3\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "b").symlink_to((bin_dir / "b").resolve())

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x" if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, _d: False,
    )
    assert rc == 0


def test_cmd_setup_dry_run_does_not_modify_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    base_dir = tmp_path / "base"
    bin_dir = tmp_path / "bin"
    base_dir.mkdir()
    bin_dir.mkdir()
    (bin_dir / "b").write_text("#!/bin/sh\n")

    home = tmp_path / "home"
    home.mkdir()
    local_bin = home / ".local" / "bin"
    local_bin.mkdir(parents=True)

    monkeypatch.setattr(setup_tools.Path, "home", lambda: home)
    monkeypatch.setattr(
        setup_tools,
        "find_executable",
        lambda name, extra_candidates=(): "/usr/bin/x" if name in {"uv", "git", "tmux"} else None,
    )
    monkeypatch.setattr(setup_tools, "_runtime_imports_ok", lambda: (True, "ok"))
    monkeypatch.setenv("PATH", f"{local_bin}:/usr/bin")

    rc = setup_tools.cmd_setup(
        base_dir,
        bin_dir,
        tmux_bin_candidates=(),
        prompt_yes_no=lambda _q, _d: True,
        dry_run=True,
    )
    assert rc == 1
    assert not (base_dir / ".homebase").exists()
    assert not (local_bin / "b").exists()
