from __future__ import annotations

import importlib
from pathlib import Path


def test_package_import() -> None:
    mod = importlib.import_module("homebase")
    assert hasattr(mod, "__version__")


def test_cli_entrypoint_callable() -> None:
    cli = importlib.import_module("homebase.cli")
    assert callable(getattr(cli, "entrypoint", None))


def test_cli_parser_builds() -> None:
    cli_parser = importlib.import_module("homebase.cli.parser")
    parser = cli_parser.build_cli_parser()
    ns = parser.parse_args(["help"])
    assert ns.command == "help"


def test_cli_parser_accepts_tmux_session() -> None:
    cli_parser = importlib.import_module("homebase.cli.parser")
    parser = cli_parser.build_cli_parser()
    ns = parser.parse_args(["--tmux-session", "main", "help"])
    assert ns.tmux_session == "main"


def test_cli_main_callable() -> None:
    entry = importlib.import_module("homebase.cli.entry")
    assert callable(getattr(entry, "main", None))


def test_cli_help_smoke(tmp_path: Path, monkeypatch, capsys) -> None:
    entry = importlib.import_module("homebase.cli.entry")
    monkeypatch.setenv("BASE_FOLDER", str(tmp_path))
    rc = int(entry.main(["help"]))
    capsys.readouterr()
    assert rc == 0


def test_cli_tmux_session_sets_process_override(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    entry = importlib.import_module("homebase.cli.entry")
    constants = importlib.import_module("homebase.core.constants")
    monkeypatch.setenv("BASE_FOLDER", str(tmp_path))
    monkeypatch.delenv(constants.ENV_TMUX_SESSION, raising=False)

    try:
        rc = int(entry.main(["--tmux-session", "main", "help"]))

        capsys.readouterr()
        assert rc == 0
        assert entry.os.environ[constants.ENV_TMUX_SESSION] == "main"
    finally:
        entry.os.environ.pop(constants.ENV_TMUX_SESSION, None)


def test_cli_ls_smoke(tmp_path: Path, monkeypatch, capsys) -> None:
    """``b ls`` returns 0 on an empty workspace (no projects → no
    output beyond an empty list)."""
    entry = importlib.import_module("homebase.cli.entry")
    monkeypatch.setenv("BASE_FOLDER", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    rc = int(entry.main(["ls"]))
    capsys.readouterr()
    assert rc == 0


def test_cli_completion_smoke(tmp_path: Path, monkeypatch, capsys) -> None:
    entry = importlib.import_module("homebase.cli.entry")
    monkeypatch.setenv("BASE_FOLDER", str(tmp_path))
    rc = int(entry.main(["completion", "fish"]))
    out = capsys.readouterr().out
    assert rc == 0
    assert "function _b_complete" in out or "complete" in out


def test_cli_shell_init_smoke(tmp_path: Path, monkeypatch, capsys) -> None:
    entry = importlib.import_module("homebase.cli.entry")
    monkeypatch.setenv("BASE_FOLDER", str(tmp_path))
    rc = int(entry.main(["shell-init"]))
    capsys.readouterr()
    assert rc == 0


def test_cli_shell_init_specific_shell(tmp_path: Path, monkeypatch, capsys) -> None:
    entry = importlib.import_module("homebase.cli.entry")
    monkeypatch.setenv("BASE_FOLDER", str(tmp_path))
    rc = int(entry.main(["shell-init", "bash"]))
    out = capsys.readouterr().out
    assert rc == 0
    assert out  # shell-init prints a script


def test_cli_internal_complete_smoke(tmp_path: Path, monkeypatch, capsys) -> None:
    entry = importlib.import_module("homebase.cli.entry")
    monkeypatch.setenv("BASE_FOLDER", str(tmp_path))
    rc = int(entry.main(["__complete", "fish", "1", "b"]))
    capsys.readouterr()
    assert rc == 0


def test_cli_help_unknown_topic_returns_2(tmp_path: Path, monkeypatch, capsys) -> None:
    entry = importlib.import_module("homebase.cli.entry")
    monkeypatch.setenv("BASE_FOLDER", str(tmp_path))
    rc = int(entry.main(["help", "ghost-topic-1234"]))
    err = capsys.readouterr().err
    assert rc == 2
    assert "unknown help topic" in err


def test_cli_help_topics_list(tmp_path: Path, monkeypatch, capsys) -> None:
    entry = importlib.import_module("homebase.cli.entry")
    monkeypatch.setenv("BASE_FOLDER", str(tmp_path))
    rc = int(entry.main(["help", "topics"]))
    capsys.readouterr()
    assert rc == 0


def test_cli_invalid_args_returns_parser_exit_code(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    entry = importlib.import_module("homebase.cli.entry")
    monkeypatch.setenv("BASE_FOLDER", str(tmp_path))
    rc = int(entry.main(["this-is-not-a-real-command"]))
    capsys.readouterr()
    assert rc != 0


def test_resolve_base_dir_uses_env_when_no_arg(tmp_path: Path, monkeypatch) -> None:
    entry = importlib.import_module("homebase.cli.entry")
    monkeypatch.setenv("BASE_FOLDER", str(tmp_path))
    assert entry.resolve_base_dir(None) == tmp_path.resolve()
