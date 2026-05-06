from __future__ import annotations

from pathlib import Path

from homebase.cli import completion as cli_completion


def test_completion_script_contains_shell_hooks() -> None:
    assert "complete -F _b_completion b" in cli_completion.completion_script("bash")
    assert "compdef _b_completion b" in cli_completion.completion_script("zsh")
    assert "complete -c b -f -a '(__b_complete)'" in cli_completion.completion_script("fish")


def test_completion_candidates_include_top_level_commands() -> None:
    out = cli_completion.completion_candidates(["st"], 1, base_dir=Path("."))
    assert "status" in out


def test_completion_candidates_support_dynamic_quick_create_keys(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_completion,
        "_quick_create_keys",
        lambda _base_dir: ["tmp", "area51"],
    )
    out = cli_completion.completion_candidates(["c", "a"], 2, base_dir=Path("."))
    assert out == ["area51"]


def test_completion_candidates_handles_trailing_space_for_quick_create(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_completion,
        "_quick_create_keys",
        lambda _base_dir: ["tmp", "area51"],
    )
    out = cli_completion.completion_candidates(["c"], 2, base_dir=Path("."))
    assert out == ["area51", "tmp"]


def test_completion_candidates_support_named_filters(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_completion,
        "_named_filter_keys",
        lambda _base_dir: ["work", "hot"],
    )
    out = cli_completion.completion_candidates(["--filter", "h"], 2, base_dir=Path("."))
    assert out == ["hot"]


def test_completion_candidates_support_regression_case_values(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_completion,
        "_regression_case_names",
        lambda: ["cache_schema", "archive_restore"],
    )
    out = cli_completion.completion_candidates(
        ["test", "regression", "--case", "a"],
        4,
        base_dir=Path("."),
    )
    assert out == ["archive_restore"]
