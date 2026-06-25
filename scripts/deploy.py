#!/usr/bin/env python3
"""Interactive release flow for homebase.

Usage:
    uv run python scripts/deploy.py   (wired as `mise run deploy`)

Flow:
    1. Launch lazygit so you can review/stage/commit working changes.
    2. After lazygit exits, ask for a semver bump (major/minor/patch/none).
    3. Bump [project].version in pyproject.toml.
    4. Write a CHANGELOG.md entry headed `## <version> - <date>`. The body
       is drafted by `claude` from the commits since the previous version
       tag; the heading itself is always built here, never by claude.
       The whole file is forced to ASCII dashes (no em/en-dash).
    5. Show the new entry and let you edit it before anything is committed.
    6. On confirmation, git add + commit the version bump (+ changelog),
       then tag vX.Y.Z. Never pushes.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"
VERSION_RE = re.compile(r'(?m)^version = "(\d+)\.(\d+)\.(\d+)"$')


def run_lazygit() -> None:
    if shutil.which("lazygit") is None:
        print("lazygit not found in PATH", file=sys.stderr)
        raise SystemExit(1)
    subprocess.run(["lazygit"], cwd=REPO_ROOT, check=False)


def read_current_version() -> tuple[int, int, int]:
    text = PYPROJECT.read_text()
    matches = VERSION_RE.findall(text)
    if len(matches) != 1:
        print(f"expected exactly one version line in {PYPROJECT}, found {len(matches)}", file=sys.stderr)
        raise SystemExit(1)
    major, minor, patch = matches[0]
    return int(major), int(minor), int(patch)


def bump(version: tuple[int, int, int], kind: str) -> tuple[int, int, int]:
    major, minor, patch = version
    if kind == "major":
        return major + 1, 0, 0
    if kind == "minor":
        return major, minor + 1, 0
    return major, minor, patch + 1


def write_version(new_version: tuple[int, int, int]) -> str:
    new_str = "%d.%d.%d" % new_version
    text = PYPROJECT.read_text()
    text, count = VERSION_RE.subn(f'version = "{new_str}"', text, count=1)
    if count != 1:
        print(f"failed to write new version into {PYPROJECT}", file=sys.stderr)
        raise SystemExit(1)
    PYPROJECT.write_text(text)
    return new_str


_FANCY_DASHES = str.maketrans({"‒": "-", "–": "-", "—": "-", "―": "-"})


def ascii_dashes(text: str) -> str:
    """Replace figure/en/em/horizontal-bar dashes with ASCII '-'."""
    return text.translate(_FANCY_DASHES)


def previous_tag() -> str:
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def commit_log_since(tag: str) -> str:
    log_range = f"{tag}..HEAD" if tag else "HEAD"
    result = subprocess.run(
        ["git", "log", log_range, "--pretty=format:- %s"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip()


def generate_changelog_body(new_version: str, commits: str) -> str | None:
    """Bullet-point body only — the `## version - date` heading is always
    built in ``write_changelog_entry`` so the format can't drift. Drafted
    from the commits since the previous version tag; never em/en-dashes."""
    if shutil.which("claude") is None:
        print("claude not found in PATH, skipping changelog body", file=sys.stderr)
        return None
    if not commits:
        print("no commits since previous version, skipping changelog body", file=sys.stderr)
        return None
    prompt = (
        f"Write the body of a terse CHANGELOG.md entry for homebase version {new_version}, "
        "single-user personal tool, no marketing language. Summarize the commits "
        "below into a few bullet points grouped by what changed (skip trivial/"
        "internal commits). Output ONLY markdown bullet points (no heading, "
        "no version/date line, nothing else). Use ASCII '-' only, never em-dash "
        f"or en-dash.\n\nCommits:\n{commits}"
    )
    result = subprocess.run(
        ["claude", "-p", prompt],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        print(f"claude changelog generation failed: {result.stderr.strip()}", file=sys.stderr)
        return None
    return ascii_dashes(result.stdout.strip())


def write_changelog_entry(version: str, body: str | None) -> None:
    heading = f"## {version} - {date.today().isoformat()}"
    entry = heading if not body else f"{heading}\n\n{body}"
    existing = CHANGELOG.read_text() if CHANGELOG.exists() else "# Changelog\n"
    lines = existing.splitlines()
    if lines and lines[0].startswith("# "):
        header, rest = lines[0], lines[1:]
        new_text = "\n".join([header, "", entry, "", *rest]).rstrip() + "\n"
    else:
        new_text = entry + "\n\n" + existing
    CHANGELOG.write_text(ascii_dashes(new_text))


def review_changelog() -> None:
    """Show the pending CHANGELOG.md and offer to edit it before commit.
    Any edits are re-sanitized so the file never keeps an em/en-dash."""
    print("\n--- CHANGELOG.md (new entry on top) ---")
    print(CHANGELOG.read_text(), end="")
    print("--- end ---")
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if not editor:
        return
    answer = input(f"Edit CHANGELOG.md in {editor} before commit? [y/N]: ").strip().lower()
    if answer not in ("y", "yes"):
        return
    subprocess.run([*editor.split(), str(CHANGELOG)], cwd=REPO_ROOT, check=False)
    CHANGELOG.write_text(ascii_dashes(CHANGELOG.read_text()))


def git_commit_and_tag(new_version: str) -> None:
    subprocess.run(["git", "add", "pyproject.toml", "CHANGELOG.md"], cwd=REPO_ROOT, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"release: bump version to {new_version}"],
        cwd=REPO_ROOT,
        check=True,
    )
    subprocess.run(["git", "tag", f"v{new_version}"], cwd=REPO_ROOT, check=True)


def main() -> int:
    run_lazygit()

    answer = input("Bump version? [major/minor/patch/none]: ").strip().lower()
    if answer in ("", "none"):
        print("skipping version bump")
        return 0
    if answer not in ("major", "minor", "patch"):
        print(f"invalid choice: {answer!r}", file=sys.stderr)
        return 1

    current = read_current_version()
    new_version = write_version(bump(current, answer))
    print(f"bumped version: {'.'.join(map(str, current))} -> {new_version}")

    commits = commit_log_since(previous_tag())
    body = generate_changelog_body(new_version, commits)
    write_changelog_entry(new_version, body)

    review_changelog()

    proceed = input(f"Commit version bump + changelog and tag v{new_version}? [y/N]: ").strip().lower()
    if proceed not in ("y", "yes"):
        print("aborted before commit; pyproject.toml + CHANGELOG.md left modified in the working tree")
        return 0

    git_commit_and_tag(new_version)
    print(f"tagged v{new_version} (not pushed). Run `git push && git push --tags` when ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
