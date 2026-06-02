from __future__ import annotations

from pathlib import Path

import pytest

from homebase.commands import setup as commands_setup
from homebase.config import store as config_store
from homebase.core.constants import (
    BASE_MARKER_FILE,
    NAMED_FILTERS,
    SAVED_FILTER_QUERIES,
)


@pytest.fixture(autouse=True)
def _clear_global() -> None:
    config_store.clear_global_config_cache()
    NAMED_FILTERS.clear()
    SAVED_FILTER_QUERIES.clear()


def test_print_help_outputs_subcommand_list(capsys) -> None:
    commands_setup.print_help()
    out = capsys.readouterr().out
    assert "b subcommands:" in out
    assert "b new" in out
    assert "b ls" in out


def test_cmd_utils_unknown_subcommand_reports_error(
    capsys, tmp_path: Path
) -> None:
    rc = commands_setup.cmd_utils(tmp_path, "ghost")
    err = capsys.readouterr().err
    assert rc == 1
    assert "unknown" in err


def test_cmd_utils_opt_in_writes_report_for_invalid_markers(
    capsys, tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "parent").mkdir()
    (tmp_path / "parent" / BASE_MARKER_FILE).write_text("")
    (tmp_path / "parent" / "child").mkdir()
    (tmp_path / "parent" / "child" / BASE_MARKER_FILE).write_text("")

    monkeypatch.setattr(
        commands_setup,
        "_prompt_yes_no",
        lambda _q, _d: True,
    )
    rc = commands_setup.cmd_utils(tmp_path, "opt-in-nested-discovery")
    out = capsys.readouterr().out
    assert rc == 2
    assert "nested discovery utility" in out


def test_cmd_recent_runs_against_empty_workspace(
    capsys, tmp_path: Path
) -> None:
    rc = commands_setup.cmd_recent(tmp_path)
    assert rc == 0
    # capture any output but do not require a specific shape
    capsys.readouterr()


def test_cmd_tags_ls_empty_workspace(capsys, tmp_path: Path) -> None:
    rc = commands_setup.cmd_tags_ls(tmp_path)
    capsys.readouterr()
    assert rc == 0


def test_cmd_ls_empty_workspace(capsys, tmp_path: Path) -> None:
    rc = commands_setup.cmd_ls(tmp_path)
    capsys.readouterr()
    assert rc == 0


def test_cmd_json_empty_workspace(capsys, tmp_path: Path) -> None:
    rc = commands_setup.cmd_json(tmp_path)
    out = capsys.readouterr().out
    assert rc == 0
    # cmd_json prints a JSON array; usually starts with "["
    assert out.lstrip().startswith("[") or out.strip() == "[]"


def test_cmd_tags_sync_runs_on_empty_workspace(capsys, tmp_path: Path) -> None:
    rc = commands_setup.cmd_tags_sync(tmp_path, verbose=False, debug=False)
    capsys.readouterr()
    assert rc in {0, 1}  # tolerate environment-specific exit codes


def test_prompt_helpers_delegate_to_prompting(monkeypatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        commands_setup.prompting,
        "prompt_readline",
        lambda prompt, **kw: (seen.append(prompt), "1")[1],
    )
    assert commands_setup._prompt_readline("Hello?", default="x") == "1"
    assert seen == ["Hello?"]


def test_prompt_yes_no_yes_path(monkeypatch) -> None:
    monkeypatch.setattr(
        commands_setup,
        "_prompt_readline",
        lambda prompt, **kw: "y",
    )
    assert commands_setup._prompt_yes_no("ok?", default=True) is True


def test_prompt_yes_no_no_path(monkeypatch) -> None:
    monkeypatch.setattr(
        commands_setup,
        "_prompt_readline",
        lambda prompt, **kw: "n",
    )
    assert commands_setup._prompt_yes_no("ok?", default=False) is False
