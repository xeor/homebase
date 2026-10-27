from __future__ import annotations

from pathlib import Path

import pytest

from homebase.commands import open_target
from homebase.core.constants import ENV_OPEN_MODE, OPEN_MODE_PROFILES


def test_open_profile_spec_falls_back_to_first() -> None:
    assert open_target.open_profile_spec("herdr_workspace")["herdr_new"] == "workspace"
    assert open_target.open_profile_spec("nope") is OPEN_MODE_PROFILES[0]


@pytest.mark.parametrize(
    ("profile", "backend"),
    [("herdr_tab_goto", "herdr"), ("tmux_tab", "tmux"), ("shell_cd", "tmux")],
)
def test_open_with_mode_routes_by_profile(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, profile: str, backend: str
) -> None:
    seen: list[tuple[str, Path]] = []
    monkeypatch.setenv(ENV_OPEN_MODE, profile)
    monkeypatch.setattr(
        open_target.herdr_panes,
        "open_with_mode",
        lambda path, spec, *, open_shell_in_dir: seen.append(("herdr", path)) or 3,
    )
    monkeypatch.setattr(
        open_target.tmux_flow,
        "open_with_mode",
        lambda base_dir, path: seen.append(("tmux", path)) or 4,
    )
    target = tmp_path / "p"
    assert open_target.open_with_mode(tmp_path, target) == (3 if backend == "herdr" else 4)
    assert seen == [(backend, target)]
