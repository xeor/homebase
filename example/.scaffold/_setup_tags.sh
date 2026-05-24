#!/usr/bin/env bash
# Builds _tags/<tag>/<name> symlink overlay from each project's tags.
# Mirrors what the `tag_symlink_sync` post-hook would do at runtime.
set -euo pipefail
BASE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$BASE"

rm -rf _tags
mkdir _tags

uv run --quiet --with pyyaml python - <<'PY'
import os, yaml
from pathlib import Path

base = Path(".")
tags_root = base / "_tags"
tags_root.mkdir(exist_ok=True)

def projects():
    # Active projects: top-level dirs (excluding _-prefixed + dotfiles)
    for p in sorted(base.iterdir()):
        if not p.is_dir() or p.name.startswith("_") or p.name.startswith("."):
            continue
        yield p
    # Archived projects: _archive/<year>/<date>_<name>/
    arch = base / "_archive"
    if arch.is_dir():
        for year in sorted(arch.iterdir()):
            if not year.is_dir():
                continue
            for proj in sorted(year.iterdir()):
                if proj.is_dir():
                    yield proj

for proj in projects():
    yml = proj / ".base.yaml"
    if not yml.is_file():
        continue
    try:
        data = yaml.safe_load(yml.read_text()) or {}
    except yaml.YAMLError:
        continue
    tags = data.get("tags") or []
    if not isinstance(tags, list):
        continue
    for tag in tags:
        if not isinstance(tag, str) or not tag.strip():
            continue
        safe = tag.strip().replace("/", "_")
        tag_dir = tags_root / safe
        tag_dir.mkdir(parents=True, exist_ok=True)
        link = tag_dir / proj.name
        if link.exists() or link.is_symlink():
            link.unlink()
        target = os.path.relpath(proj.resolve(), tag_dir.resolve())
        link.symlink_to(target)
PY

echo "tag symlinks:"
find _tags -maxdepth 2 -mindepth 2 | wc -l
