from __future__ import annotations

import re
import tomllib
from pathlib import Path

from homebase.core import version as core_version

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[+\-].+)?$")
_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_get_version_matches_pyproject_and_is_semver() -> None:
    pyproject = tomllib.loads(_PYPROJECT.read_text())
    expected = pyproject["project"]["version"]
    actual = core_version.get_version()
    assert actual == expected
    assert _SEMVER_RE.match(actual)


def test_get_commit_returns_non_empty_string() -> None:
    commit = core_version.get_commit()
    assert isinstance(commit, str)
    assert commit
