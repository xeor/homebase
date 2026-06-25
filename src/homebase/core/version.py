from __future__ import annotations

import subprocess
from functools import lru_cache
from importlib import metadata
from pathlib import Path

_PACKAGE_NAME = "homebase"
REPO_ROOT = Path(__file__).resolve().parents[3]


def get_version() -> str:
    try:
        return metadata.version(_PACKAGE_NAME)
    except metadata.PackageNotFoundError:
        return "0.0.0+unknown"


@lru_cache(maxsize=1)
def get_commit() -> str:
    if not (REPO_ROOT / ".git").exists():
        return "unknown"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return "unknown"
    if result.returncode != 0:
        return "unknown"
    return result.stdout.strip() or "unknown"
