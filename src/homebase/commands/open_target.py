from __future__ import annotations

from pathlib import Path

from ..config.prefs import load_open_mode_config
from ..core.constants import OPEN_MODE_CONFIG, OPEN_MODE_PROFILES
from ..herdr import panes as herdr_panes
from ..tmux import flow as tmux_flow


def open_profile_spec(profile: str) -> dict[str, object]:
    """The OPEN_MODE_PROFILES entry for ``profile`` (first one if unknown)."""
    return next(
        (p for p in OPEN_MODE_PROFILES if str(p.get("id")) == profile),
        OPEN_MODE_PROFILES[0],
    )


def open_with_mode(base_dir: Path, path: Path) -> int:
    """`b open` / picking a project: herdr profiles go to herdr, the rest to tmux."""
    conf = load_open_mode_config(base_dir)
    spec = open_profile_spec(str(conf.get("profile", OPEN_MODE_CONFIG["profile"])))
    if spec.get("backend") == "herdr":
        return herdr_panes.open_with_mode(
            path, spec, open_shell_in_dir=tmux_flow.open_shell_in_dir
        )
    return tmux_flow.open_with_mode(base_dir, path)
