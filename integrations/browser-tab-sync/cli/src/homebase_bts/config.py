"""Config and runtime paths. XDG on Linux/macOS."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "homebase-bts"


def config_file() -> Path:
    return config_dir() / "config.toml"


def state_db() -> Path:
    return config_dir() / "state.sqlite"


def sim_store() -> Path:
    """Persisted state for the local (no-browser) development backend."""
    return config_dir() / "sim-browser.json"


def runtime_dir() -> Path:
    """Private runtime dir for ephemeral IPC state."""
    override = os.environ.get("HBTS_RUNTIME_DIR")
    if override:
        return Path(override) / "homebase-bts"
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        return Path(xdg) / "homebase-bts"
    return Path(tempfile.gettempdir()) / f"homebase-bts-{os.getuid()}"


def host_sock() -> Path:
    """Unix socket the native host listens on for ad-hoc CLI commands."""
    return runtime_dir() / "host.sock"


def sync_store() -> Path:
    """Persisted host-side two-way sync targets (survive host/browser restarts)."""
    return config_dir() / "sync.json"


def log_dir() -> Path:
    return config_dir() / "logs"


def log_file() -> Path:
    return log_dir() / "homebase-bts.log"


def ensure_dirs() -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    log_dir().mkdir(parents=True, exist_ok=True)
    runtime_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime_dir().chmod(0o700)
