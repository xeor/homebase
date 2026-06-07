"""Native messaging host manifest install/uninstall + doctor checks.

The manifest tells a browser which executable to spawn for our host name and
which extension may connect. macOS manifest dirs are per *browser variant*
(not per profile), so installing is an explicit, single-browser action — never
a shotgun across every browser on the machine. Use an isolated dev browser
(e.g. Chromium) to keep your daily Chrome/Vivaldi untouched.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import sysconfig
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from homebase_bts import config
from homebase_bts.protocol import EnsureResult, HealthCheck, recv_frame, send_frame

HOST_NAME = "nu.boa.homebase_bts"


class Browser(StrEnum):
    chrome = "chrome"
    chrome_beta = "chrome-beta"
    chrome_canary = "chrome-canary"
    chrome_for_testing = "chrome-for-testing"
    chromium = "chromium"
    vivaldi = "vivaldi"
    brave = "brave"
    edge = "edge"


# Relative path under ~/Library/Application Support for each variant.
_REL: dict[Browser, str] = {
    Browser.chrome: "Google/Chrome",
    Browser.chrome_beta: "Google/Chrome Beta",
    Browser.chrome_canary: "Google/Chrome Canary",
    Browser.chrome_for_testing: "Google/Chrome for Testing",
    Browser.chromium: "Chromium",
    Browser.vivaldi: "Vivaldi",
    Browser.brave: "BraveSoftware/Brave-Browser",
    Browser.edge: "Microsoft Edge",
}


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _support_dir() -> Path:
    return Path.home() / "Library" / "Application Support"


def manifest_dir(browser: Browser) -> Path:
    return _support_dir() / _REL[browser] / "NativeMessagingHosts"


def all_manifest_dirs() -> list[Path]:
    return [_support_dir() / rel / "NativeMessagingHosts" for rel in _REL.values()]


def extension_id_for_path(path: Path) -> str:
    """Chrome's unpacked-extension ID for a load path.

    sha256(absolute path) -> first 16 bytes -> each hex nibble mapped 0-f to a-p.
    Lets dev compute the ID WXT will get, without reading chrome://extensions.
    """
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:32]
    return "".join(chr(ord("a") + int(c, 16)) for c in digest)


def host_executable() -> Path:
    """Absolute path to the homebase-bts-host console script."""
    found = shutil.which("homebase-bts-host")
    if found:
        return Path(found)
    return Path(sysconfig.get_path("scripts")) / "homebase-bts-host"


def _manifest(extension_id: str) -> dict[str, object]:
    return {
        "name": HOST_NAME,
        "description": "homebase-bts native messaging host",
        "path": str(host_executable()),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }


def install_native_host(
    extension_id: str,
    *,
    browser: Browser | None = None,
    directory: Path | None = None,
) -> Path:
    """Write the manifest into a single browser's dir. Explicit by design."""
    target = directory if directory is not None else manifest_dir(_require(browser))
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{HOST_NAME}.json"
    path.write_text(json.dumps(_manifest(extension_id), indent=2) + "\n", encoding="utf-8")
    return path


def uninstall_native_host(dirs: list[Path] | None = None) -> list[Path]:
    """Remove our manifest wherever it exists (safe: only our own file)."""
    removed: list[Path] = []
    for directory in dirs if dirs is not None else all_manifest_dirs():
        path = directory / f"{HOST_NAME}.json"
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed


def _require(browser: Browser | None) -> Browser:
    if browser is None:
        raise ValueError("a browser or directory is required")
    return browser


def doctor() -> list[Check]:
    checks: list[Check] = []

    exe = host_executable()
    checks.append(Check("host executable", exe.exists(), str(exe)))

    locations = [d / f"{HOST_NAME}.json" for d in all_manifest_dirs()]
    dev_profile = os.environ.get("HBTS_DEV_PROFILE")
    if dev_profile:
        locations.insert(0, Path(dev_profile) / "NativeMessagingHosts" / f"{HOST_NAME}.json")
    present = [p for p in locations if p.exists()]
    checks.append(
        Check(
            "native host manifest",
            bool(present),
            ", ".join(str(p) for p in present) or "not installed (run mise run host:install-dev)",
        )
    )

    sock = config.host_sock()
    checks.append(
        Check(
            "host socket (browser running)",
            sock.exists(),
            str(sock) if sock.exists() else "no socket — browser/extension not connected",
        )
    )
    if sock.exists():
        checks.append(_check_host_roundtrip(sock))
    return checks


def _check_host_roundtrip(sock_path: Path, timeout: float = 2.0) -> Check:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(str(sock_path))
        request_id = str(uuid.uuid4())
        send_frame(sock, HealthCheck(request_id=request_id))
        reply = recv_frame(sock)
    except (OSError, TimeoutError) as exc:
        return Check(
            "host roundtrip",
            False,
            f"no extension response within {timeout:g}s ({exc})",
        )
    finally:
        sock.close()
    if not isinstance(reply, EnsureResult):
        detail = "host closed connection" if reply is None else f"unexpected reply: {reply.type}"
        return Check("host roundtrip", False, detail)
    if not reply.ok:
        return Check(
            "host roundtrip",
            False,
            reply.error or "extension rejected health check",
        )
    return Check("host roundtrip", True, "extension responded")
