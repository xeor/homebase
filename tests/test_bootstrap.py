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


def test_cli_main_callable() -> None:
    entry = importlib.import_module("homebase.cli.entry")
    assert callable(getattr(entry, "main", None))


def test_cli_help_smoke(tmp_path: Path, monkeypatch, capsys) -> None:
    entry = importlib.import_module("homebase.cli.entry")
    monkeypatch.setenv("BASE_FOLDER", str(tmp_path))
    rc = int(entry.main(["help"]))
    capsys.readouterr()
    assert rc == 0


def test_cli_status_smoke(tmp_path: Path, monkeypatch, capsys) -> None:
    entry = importlib.import_module("homebase.cli.entry")
    monkeypatch.setenv("BASE_FOLDER", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    rc = int(entry.main(["status"]))
    capsys.readouterr()
    assert rc == 0
