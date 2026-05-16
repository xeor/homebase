from __future__ import annotations

import re

_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")
_SSH_GIT_RE = re.compile(r"^[a-zA-Z0-9_.\-]+@[a-zA-Z0-9_.\-]+:")


def is_url(value: str) -> bool:
    return bool(_URL_SCHEME_RE.match(value)) or bool(_SSH_GIT_RE.match(value))


def is_path_shaped(value: str) -> bool:
    if not value:
        return False
    if is_url(value):
        return False
    if value in {".", ".."}:
        return True
    if value.startswith(("./", "../", "/", "~")):
        return True
    if value.endswith(("/", "\\")):
        return True
    if "/" in value or "\\" in value:
        return True
    return False


def classify_input(value: str | None) -> str:
    """Return one of: "empty", "url", "path"."""
    if value is None or value == "":
        return "empty"
    if is_url(value):
        return "url"
    if is_path_shaped(value):
        return "path"
    return "bare"
