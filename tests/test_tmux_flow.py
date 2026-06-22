from __future__ import annotations

from pathlib import Path

from homebase.tmux import flow as tmux_flow


def test_open_with_mode_delegates_outside_tmux(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "project"
    calls: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        tmux_flow.tmux_external,
        "is_inside_current_tmux_pane",
        lambda: False,
    )
    monkeypatch.setattr(
        tmux_flow.tmux_external,
        "open_with_mode_outside_tmux",
        lambda base_dir, path, *, open_shell_in_dir: (
            calls.append((base_dir, path)) or 7
        ),
    )

    assert tmux_flow.open_with_mode(tmp_path, target) == 7
    assert calls == [(tmp_path, target)]
