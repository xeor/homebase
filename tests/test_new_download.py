from __future__ import annotations

import http.server
import socketserver
import threading
from pathlib import Path

import pytest

from homebase.cli.parser import build_cli_parser
from homebase.workspace.new import cmd_new


@pytest.fixture
def http_root(tmp_path: Path):
    serve_dir = tmp_path / "serve"
    serve_dir.mkdir()
    (serve_dir / "hello.txt").write_text("hi there\n")

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(serve_dir), **kwargs)

        def log_message(self, format, *args):  # silence
            return

    with socketserver.TCPServer(("127.0.0.1", 0), _Handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{port}", serve_dir
        finally:
            httpd.shutdown()
            thread.join(timeout=2)


def _run(base: Path, cwd: Path, args: list[str]) -> int:
    ns = build_cli_parser().parse_args(["new", *args])
    return cmd_new(ns, base, cwd)


def test_download_fetches_file(tmp_path: Path, http_root) -> None:
    url_base, _ = http_root
    base = tmp_path / "base"
    base.mkdir()
    rc = _run(base, tmp_path, [f"{url_base}/hello.txt", "fetched"])
    assert rc == 0
    proj = base / "fetched"
    assert proj.is_dir()
    assert (proj / ".base.yaml").is_file()
    assert (proj / "hello.txt").read_text() == "hi there\n"


def test_download_failed_url_rolls_back(tmp_path: Path, http_root) -> None:
    url_base, _ = http_root
    base = tmp_path / "base"
    base.mkdir()
    rc = _run(base, tmp_path, [f"{url_base}/missing.bin", "ghost"])
    assert rc == 1
    assert not (base / "ghost").exists()


def test_download_dry_run(tmp_path: Path, http_root) -> None:
    url_base, _ = http_root
    base = tmp_path / "base"
    base.mkdir()
    rc = _run(base, tmp_path, [f"{url_base}/hello.txt", "preview", "--dry-run"])
    assert rc == 0
    assert not (base / "preview").exists()


def test_download_url_rewrites_via_config(tmp_path: Path, http_root) -> None:
    url_base, _ = http_root
    base = tmp_path / "base"
    base.mkdir()
    cfg_dir = base / ".homebase"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        "new:\n"
        "  sources:\n"
        "    download:\n"
        "      config:\n"
        "        url_rewrites:\n"
        f"          - match: '^{url_base}/redirect/(.+)$'\n"
        f"            rewrite: '{url_base}/\\1'\n"
    )
    rc = _run(base, tmp_path, [f"{url_base}/redirect/hello.txt", "rewritten"])
    assert rc == 0
    assert (base / "rewritten" / "hello.txt").read_text() == "hi there\n"
