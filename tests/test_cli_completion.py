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


def test_completion_candidates_new_mode_flags() -> None:
    out = cli_completion.completion_candidates(["new", "--"], 2, base_dir=Path("."))
    assert "--empty" in out
    assert "--local" in out
    assert "--git" in out
    assert "--download" in out
    assert "--downloaded" in out


def test_completion_candidates_new_as_uses_child_sources(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_completion,
        "_new_child_source_keys",
        lambda _base_dir: ["scratch", "prj"],
    )
    out = cli_completion.completion_candidates(["new", "--as", "s"], 3, base_dir=Path("."))
    assert out == ["scratch"]


def test_completion_candidates_new_template(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_completion,
        "_new_template_keys",
        lambda _base_dir: ["python-uv", "rust"],
    )
    out = cli_completion.completion_candidates(
        ["new", "--template", "r"], 3, base_dir=Path(".")
    )
    assert out == ["rust"]


def test_completion_includes_n_alias() -> None:
    out = cli_completion.completion_candidates([""], 1, base_dir=Path("."))
    assert "n" in out
    assert "new" in out


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
