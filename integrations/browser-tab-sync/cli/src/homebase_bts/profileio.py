"""Profile file load + atomic write + folder resolution."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import yaml

from homebase_bts.models import Profile

FOLDER_CANDIDATES = (".base-bts.yaml", ".base-bts.yml", ".homebase-bts.json", "homebase-bts.json")


def resolve(arg: str) -> Path:
    """Resolve a CLI argument to a profile file. Folders search candidates in order."""
    path = Path(arg)
    if not path.is_absolute():
        path = invocation_cwd() / path
    if path.is_dir():
        for name in FOLDER_CANDIDATES:
            candidate = path / name
            if candidate.is_file():
                return candidate
        looked = ", ".join(FOLDER_CANDIDATES)
        raise FileNotFoundError(f"no profile file in {path} (looked for {looked})")
    return path


def invocation_cwd() -> Path:
    """Directory the user invoked the command from, even when a task runner cd'd."""
    mise_cwd = os.environ.get("MISE_ORIGINAL_CWD")
    if mise_cwd:
        return Path(mise_cwd)
    return Path.cwd()


def load(path: Path) -> Profile:
    body = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(body)
        return Profile.model_validate(data)
    return Profile.model_validate_json(body)


def write_atomic(path: Path, profile: Profile, *, history: bool = True) -> None:
    """Atomic write: temp + fsync + rename, with optional history backup."""
    payload = profile.model_dump(by_alias=True)
    if path.suffix in {".yaml", ".yml"}:
        data = yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)
    else:
        data = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    if history and path.exists():
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
        hist_dir = path.parent / ".homebase-bts" / "history"
        hist_dir.mkdir(parents=True, exist_ok=True)
        _write_bytes_atomic(hist_dir / f"{path.stem}.{stamp}{path.suffix}", path.read_bytes())

    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise

    dir_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError:
        Path(tmp).unlink(missing_ok=True)
        raise
