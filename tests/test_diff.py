from __future__ import annotations

from homebase.core.diff import color_diff_lines, diff_counts


def test_color_diff_lines_marks_removed_and_added() -> None:
    diff = color_diff_lines(
        ["alpha", "beta", "gamma"],
        ["alpha", "BETA", "gamma"],
    )
    joined = "\n".join(diff)
    assert "bright_red" in joined
    assert "bright_green" in joined
    assert "-beta" in joined
    assert "+BETA" in joined


def test_color_diff_lines_handles_identical_inputs() -> None:
    diff = color_diff_lines(["alpha"], ["alpha"])
    assert any("no differences" in line for line in diff)


def test_color_diff_lines_truncates_long_diffs() -> None:
    current = [f"line{i}" for i in range(200)]
    desired = [f"line{i}+" for i in range(200)]
    diff = color_diff_lines(current, desired, max_lines=20)
    assert len(diff) <= 21
    assert any("truncated" in line for line in diff)


def test_diff_counts_removed_and_added() -> None:
    assert diff_counts(["a", "b", "c"], ["a", "c"]) == (1, 0)
    assert diff_counts(["a"], ["a", "b", "c"]) == (0, 2)
    assert diff_counts(["a", "b"], ["a", "B"]) == (1, 1)
    assert diff_counts(["a"], ["a"]) == (0, 0)
