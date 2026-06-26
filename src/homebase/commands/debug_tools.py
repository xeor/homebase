from __future__ import annotations

import io
import shutil
import subprocess
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

from ..core.setup_model import SetupDebugTool

_QA_STATUS_MARKER = "Status snapshot"


def build_dev_debug_tools(base_dir: Path) -> list[SetupDebugTool]:
    """Developer / environment utilities for the setup Debug tab. These
    complement the tmux focus diagnostics with benchmark, test and QA
    shortcuts so the menu is useful as a one-stop dashboard."""
    return [
        SetupDebugTool(
            id="env_report",
            label="Environment report",
            description=(
                "Python, platform, homebase version, tmux, pyobjc and "
                "source-checkout detection. Cheap and always safe to run."
            ),
            run=lambda: _env_report(base_dir),
        ),
        SetupDebugTool(
            id="run_benchmark",
            label="Run performance benchmark",
            description=(
                "Run the synthetic workspace benchmark (`b benchmark run`) "
                "on a throwaway base folder and capture its full output. "
                "Takes a few seconds."
            ),
            run=lambda: _run_benchmark(base_dir),
        ),
        SetupDebugTool(
            id="run_pytest",
            label="Run pytest (source checkout)",
            description=(
                "Run the test suite via `uv run pytest -q`. Only available "
                "from a source checkout; otherwise reports that it is not."
            ),
            run=_run_pytest,
        ),
        SetupDebugTool(
            id="qa_summary",
            label="QA summary (ruff + status snapshot)",
            description=(
                "Run `ruff check` and echo the QA status snapshot from "
                "docs/QA/README.md. Source checkout only."
            ),
            run=_qa_summary,
        ),
    ]


# --- helpers ---------------------------------------------------------


def _esc(text: object) -> str:
    from rich.markup import escape

    return escape(str(text))


def _ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f} ms"


def _repo_root() -> Path | None:
    """Walk up from this package looking for the source checkout
    (a ``pyproject.toml`` naming homebase next to a ``tests`` dir).
    Returns ``None`` for a wheel/site-packages install."""
    for parent in Path(__file__).resolve().parents:
        pyproject = parent / "pyproject.toml"
        if not pyproject.is_file():
            continue
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            continue
        if 'name = "homebase"' in text and (parent / "tests").is_dir():
            return parent
    return None


def _run(cmd: list[str], cwd: Path, *, timeout: float) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return proc.returncode, (proc.stdout + proc.stderr).rstrip()


def _ok(rc: int) -> str:
    return "[bright_green]ok[/]" if rc == 0 else "[bright_red]failed[/]"


# --- environment report ----------------------------------------------


def _env_report(base_dir: Path) -> str:
    from ..core.version import get_version

    lines = ["[bold]Environment report[/]", ""]
    lines.append(f"homebase version: {_esc(get_version())}")
    lines.append(f"python:           {_esc(sys.version.split()[0])} ({_esc(sys.executable)})")
    lines.append(f"platform:         {_esc(sys.platform)}")
    lines.append(f"base folder:      {_esc(base_dir)}")

    repo = _repo_root()
    lines.append(
        f"source checkout:  {_esc(repo) if repo is not None else '[dim]no (installed package)[/]'}"
    )

    tmux_bin = shutil.which("tmux")
    if tmux_bin:
        rc, out = _run([tmux_bin, "-V"], base_dir, timeout=5.0)
        lines.append(f"tmux:             {_esc(out.strip()) if rc == 0 else '<version probe failed>'} ({_esc(tmux_bin)})")
    else:
        lines.append("tmux:             [bright_yellow]not on PATH[/]")

    try:
        from AppKit import NSRunningApplication  # noqa: F401

        pyobjc = "[bright_green]installed[/]"
    except ImportError as exc:
        pyobjc = f"[bright_yellow]not installed[/] ({_esc(exc)})"
    lines.append(f"pyobjc (AppKit):  {pyobjc}")

    for tool in ("uv", "pytest", "ruff"):
        path = shutil.which(tool)
        lines.append(
            f"{tool + ':':17} {_esc(path) if path else '[dim]not on PATH[/]'}"
        )
    return "\n".join(lines)


# --- benchmark -------------------------------------------------------


def _run_benchmark(base_dir: Path) -> str:
    from ..workspace.benchmark import cmd_benchmark_run

    lines = ["[bold]Performance benchmark[/]", ""]
    buffer = io.StringIO()
    start = time.perf_counter()
    rc = 1
    try:
        with redirect_stdout(buffer):
            rc = cmd_benchmark_run(base_dir, base_dir)
    except (OSError, RuntimeError, ValueError) as exc:
        lines.append(f"[bright_red]benchmark raised {type(exc).__name__}: {_esc(exc)}[/]")
    elapsed = time.perf_counter() - start
    lines.append(f"exit: {_ok(rc)}   wall: {_ms(elapsed)}")
    lines.append("")
    output = buffer.getvalue().rstrip()
    lines.append(_esc(output) if output else "[dim](no output)[/]")
    return "\n".join(lines)


# --- pytest ----------------------------------------------------------


def _run_pytest() -> str:
    lines = ["[bold]pytest[/]", ""]
    repo = _repo_root()
    if repo is None:
        lines.append(
            "[bright_yellow]not a source checkout[/] — the test suite is not "
            "shipped with the installed package, so pytest cannot run here."
        )
        return "\n".join(lines)
    if shutil.which("uv") is None:
        lines.append("[bright_yellow]`uv` not on PATH[/] — cannot run the test suite.")
        return "\n".join(lines)
    lines.append(f"repo: {_esc(repo)}")
    start = time.perf_counter()
    rc, out = _run(["uv", "run", "pytest", "-q"], repo, timeout=600.0)
    elapsed = time.perf_counter() - start
    lines.append(f"exit: {_ok(rc)}   wall: {_ms(elapsed)}")
    lines.append("")
    lines.append(_esc(out) if out else "[dim](no output)[/]")
    return "\n".join(lines)


# --- QA summary ------------------------------------------------------


def _qa_summary() -> str:
    lines = ["[bold]QA summary[/]", ""]
    repo = _repo_root()
    if repo is None:
        lines.append(
            "[bright_yellow]not a source checkout[/] — QA tooling and "
            "docs/QA are not part of the installed package."
        )
        return "\n".join(lines)
    if shutil.which("uv") is None:
        lines.append("[bright_yellow]`uv` not on PATH[/] — cannot run ruff.")
        return "\n".join(lines)

    lines.append(f"repo: {_esc(repo)}")
    lines.append("")
    lines.append("[bold]ruff check src/homebase/ tests/[/]")
    rc, out = _run(
        ["uv", "run", "ruff", "check", "src/homebase/", "tests/"],
        repo,
        timeout=120.0,
    )
    lines.append(f"  {_ok(rc)}")
    if out:
        lines.append(_esc(out))

    lines.append("")
    lines.append("[bold]QA status snapshot (docs/QA/README.md)[/]")
    lines.extend(_qa_status_snapshot(repo))
    return "\n".join(lines)


def _qa_status_snapshot(repo: Path) -> list[str]:
    readme = repo / "docs" / "QA" / "README.md"
    if not readme.is_file():
        return ["  [dim]docs/QA/README.md not found.[/]"]
    try:
        text = readme.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"  [bright_red]read failed: {_esc(exc)}[/]"]
    out: list[str] = []
    capturing = False
    for line in text.splitlines():
        if _QA_STATUS_MARKER in line:
            capturing = True
            out.append("  " + _esc(line.lstrip("# ").strip()))
            continue
        if capturing:
            stripped = line.strip()
            if stripped.startswith("#") and out:
                break
            if stripped:
                out.append("  " + _esc(stripped))
            if len(out) > 30:
                out.append("  [dim]…(truncated)[/]")
                break
    if not out:
        return ["  [dim](no status snapshot section found)[/]"]
    return out
