from __future__ import annotations

from pathlib import Path

from homebase.ui.screens.rename import _similar_matches


def test_similar_matches_picks_exact_then_prefix(tmp_path: Path) -> None:
    for name in ("alpha", "alphabet", "beta", "gamma"):
        (tmp_path / name).mkdir()
    hits = _similar_matches(tmp_path, "alph")
    names = [n for n, _ in hits]
    assert "alpha" in names
    assert "alphabet" in names
    # `beta` is too dissimilar.
    assert "beta" not in names


def test_similar_matches_skips_underscore_dirs(tmp_path: Path) -> None:
    (tmp_path / "_archive").mkdir()
    (tmp_path / ".cache").mkdir()
    (tmp_path / "alpha").mkdir()
    hits = _similar_matches(tmp_path, "a")
    names = [n for n, _ in hits]
    # 1-char queries are skipped (limit >= 2), so nothing matches.
    assert names == []


def test_similar_matches_excludes_current_name(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    (tmp_path / "alphabet").mkdir()
    hits = _similar_matches(tmp_path, "alpha", exclude="alpha")
    names = [n for n, _ in hits]
    assert "alpha" not in names
    assert "alphabet" in names


def test_similar_matches_empty_query_returns_none(tmp_path: Path) -> None:
    (tmp_path / "alpha").mkdir()
    assert _similar_matches(tmp_path, "") == []
    assert _similar_matches(tmp_path, " ") == []
