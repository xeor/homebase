from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

from ....metadata.api import append_base_log, ensure_base_marker, save_base_tags
from ....workspace.projects import cache_upsert_project_fast
from ..base import NewContext, NewOptions, NewPlan, NewResult, Source
from ..name import resolve_final_name
from ..registry import register_source

_DEFAULT_FOLDER = "~/Downloads"
_DEFAULT_LIST_COUNT = 5


def _list_recent_files(folder: Path, limit: int) -> list[Path]:
    """Return up to ``limit`` most-recently-modified files in
    ``folder``, newest first. Hidden files (leading ``.``) are
    skipped — they're typically system metadata (``.DS_Store``,
    download stubs like ``.com.apple.Safari.WebKit.partial``, etc.)
    and never something the user actually wants to grab."""
    candidates: list[Path] = []
    for entry in folder.iterdir():
        if not entry.is_file():
            continue
        if entry.name.startswith("."):
            continue
        candidates.append(entry)
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[:max(1, limit)]


def _format_age(mtime: float, now: float | None = None) -> str:
    """Render an mtime as a coarse "N units ago" string."""
    now = time.time() if now is None else now
    delta = max(0.0, now - mtime)
    if delta < 60:
        return f"{int(delta)}s ago"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    return f"{int(delta // 86400)}d ago"


def _format_size(num_bytes: int) -> str:
    """Render a byte count as ``N B`` / ``N.N KB`` / ``N.N MB`` / etc."""
    n = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0:
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


# ANSI colors for the picker. Keys (labels) are dim cyan; values get
# their own colors so the eye snaps to what changed.
_C_RESET = "\x1b[0m"
_C_DIM = "\x1b[2m"
_C_KEY = "\x1b[36m"        # cyan        — labels (modified, size, from)
_C_NAME = "\x1b[1;97m"     # bright bold — filename
_C_AGE = "\x1b[32m"        # green       — when downloaded
_C_SIZE = "\x1b[35m"       # magenta     — file size
_C_FROM = "\x1b[33m"       # yellow      — source URL
_C_CURSOR = "\x1b[1;33m"   # bold yellow — selection caret
_C_HEAD = "\x1b[1;36m"     # bold cyan   — header
_C_HINT = "\x1b[2;37m"     # dim white   — keybinding hint


def _where_from(path: Path) -> str | None:
    """Best-effort: return the source URL the file was downloaded
    from. macOS stores this in ``kMDItemWhereFroms``; we shell out to
    ``mdls`` to read it. Returns None on any error or unsupported OS."""
    if sys.platform != "darwin":
        return None
    if shutil.which("mdls") is None:
        return None
    try:
        proc = subprocess.run(
            ["mdls", "-name", "kMDItemWhereFroms", "-raw", str(path)],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    out = (proc.stdout or "").strip()
    if not out or out == "(null)":
        return None
    # mdls -raw renders the array on multiple lines like:
    #   (
    #       "https://example.com/x",
    #       "https://referrer"
    #   )
    # Take the first non-empty quoted entry.
    for line in out.splitlines():
        line = line.strip().strip(",").strip()
        if line.startswith('"') and line.endswith('"') and len(line) >= 2:
            return line[1:-1]
    return None


def _interactive_capable() -> bool:
    """True only when both stdin and stdout are real interactive
    terminals — we need stdin for raw-mode key reads and stdout for
    redrawing the picker UI."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (OSError, ValueError):
        return False


def _render_picker(files: list[Path], selected: int) -> None:
    """Redraw the picker. To kill flicker we never issue a full
    ``\\x1b[2J`` clear after the first frame — instead we move the
    cursor home (``\\x1b[H``), then clear-to-end-of-line (``\\x1b[K``)
    on each row as we overwrite it, and clear-below (``\\x1b[J``) at
    the end. The whole frame is also a single ``sys.stdout.write`` so
    the terminal renders it atomically rather than in chunks."""
    out: list[str] = ["\x1b[H"]
    out.append(f"{_C_HEAD}Pick a recent download{_C_RESET}\x1b[K\n")
    out.append("\x1b[K\n")  # blank line under header
    for idx, path in enumerate(files):
        try:
            stat = path.stat()
            mtime = stat.st_mtime
            size = stat.st_size
        except OSError:
            mtime = 0.0
            size = 0
        age = _format_age(mtime)
        size_str = _format_size(size)
        where = _where_from(path) or "-"
        is_sel = idx == selected
        caret = f"{_C_CURSOR}>{_C_RESET}" if is_sel else " "
        idx_tag = f"{_C_CURSOR}[{idx}]{_C_RESET}" if is_sel else f"{_C_DIM}[{idx}]{_C_RESET}"
        out.append(f"{caret} {idx_tag} {_C_NAME}{path.name}{_C_RESET}\x1b[K\n")
        out.append(f"        {_C_KEY}modified:{_C_RESET} {_C_AGE}{age}{_C_RESET}\x1b[K\n")
        out.append(f"        {_C_KEY}size:    {_C_RESET} {_C_SIZE}{size_str}{_C_RESET}\x1b[K\n")
        if where == "-":
            from_val = f"{_C_DIM}-{_C_RESET}"
        else:
            from_val = f"{_C_FROM}{where}{_C_RESET}"
        out.append(f"        {_C_KEY}from:    {_C_RESET} {from_val}\x1b[K\n")
        out.append("\x1b[K\n")  # blank separator between entries
    out.append(
        f"{_C_HINT}[ up/down to move, 0-9 to jump, "
        f"enter to confirm, esc to cancel ]{_C_RESET}\x1b[K\n"
    )
    out.append("\x1b[J")  # erase any leftovers below the last frame
    sys.stdout.write("".join(out))
    sys.stdout.flush()


def _read_key() -> str:
    """Read one logical keystroke. Returns 'up', 'down', 'enter',
    'esc', a single digit char, or '' for anything we don't care
    about. Raw-mode termios required — caller must guarantee it's
    enabled."""
    ch = sys.stdin.read(1)
    if ch == "\x1b":
        # Escape or escape sequence — peek one more.
        nxt = sys.stdin.read(1)
        if nxt != "[":
            return "esc"
        code = sys.stdin.read(1)
        if code == "A":
            return "up"
        if code == "B":
            return "down"
        return ""
    if ch in ("\r", "\n"):
        return "enter"
    if ch.isdigit():
        return ch
    return ""


def _interactive_choose(
    files: list[Path],
    *,
    picker_override: object = None,
) -> Path | None:
    """Interactive picker. Returns the chosen Path, or None if the
    user cancelled (Esc / Ctrl-C / no choice). ``picker_override`` is
    a test hook — when set, it's called as a function and its return
    value (an integer index) is used directly."""
    if picker_override is not None:
        try:
            idx = int(picker_override(files))
        except (TypeError, ValueError):
            return None
        if 0 <= idx < len(files):
            return files[idx]
        return None
    if not files:
        return None
    # Lazy import — termios / tty are POSIX-only and we want the
    # module to remain importable on Windows.
    try:
        import termios
        import tty
    except ImportError:
        return None
    fd = sys.stdin.fileno()
    try:
        original = termios.tcgetattr(fd)
    except (termios.error, OSError):
        return None
    selected = 0
    # Alternate screen buffer keeps the picker from disturbing the
    # surrounding terminal scrollback; hidden cursor avoids the
    # caret jumping around during redraws.
    sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J")
    sys.stdout.flush()
    try:
        tty.setcbreak(fd)
        while True:
            _render_picker(files, selected)
            try:
                key = _read_key()
            except (OSError, ValueError):
                return None
            if key == "enter":
                return files[selected]
            if key == "esc":
                return None
            if key == "up":
                selected = max(0, selected - 1)
            elif key == "down":
                selected = min(len(files) - 1, selected + 1)
            elif key.isdigit():
                idx = int(key)
                if 0 <= idx < len(files):
                    return files[idx]
    except KeyboardInterrupt:
        return None
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)
        # Show cursor + leave alt screen.
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


@register_source
class DownloadedSource(Source):
    key = "downloaded"
    help_short = "Take a recently-downloaded file from ~/Downloads."
    accepts_input = False
    default_options = {
        "tmp": True,
        "timestamp": True,
        "open": True,
        "confirm": True,
    }
    default_config = {
        "folder": _DEFAULT_FOLDER,
        "list_count": _DEFAULT_LIST_COUNT,
    }

    # Optional hook overridden by tests so the interactive picker is
    # bypassed without touching termios / sys.stdin. Returns the
    # selected index (0 = newest); ``None`` means "no choice, use
    # default".
    _picker_override: object = None

    def _folder(self) -> Path:
        raw = self.config.get("folder") or _DEFAULT_FOLDER
        return Path(str(raw)).expanduser()

    def _list_count(self) -> int:
        raw = self.config.get("list_count", _DEFAULT_LIST_COUNT)
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return _DEFAULT_LIST_COUNT

    def _recent(self) -> list[Path]:
        folder = self._folder()
        if not folder.is_dir():
            raise ValueError(f"downloads folder not found: {folder}")
        files = _list_recent_files(folder, self._list_count())
        if not files:
            raise ValueError(f"no files in downloads folder: {folder}")
        return files

    def detects(self, raw_input, ctx: NewContext) -> bool:
        # Triggered exclusively by --downloaded; never auto-detected.
        return False

    def prepare(self, ns: object, ctx: NewContext) -> None:
        """Decide which downloaded file to use. Interactive when stdin
        + stdout are real TTYs and ``--yes`` wasn't passed; otherwise
        defaults to the newest non-hidden file (current behavior)."""
        try:
            files = self._recent()
        except ValueError:
            # plan() will raise the same error with full context; we
            # just don't try to pick interactively when there's
            # nothing to pick from.
            self._picked = None
            return
        if getattr(ns, "yes", False) or not _interactive_capable():
            self._picked = files[0]
            return
        chosen = _interactive_choose(files, picker_override=type(self)._picker_override)
        self._picked = chosen if chosen is not None else files[0]

    def _pick(self) -> Path:
        picked = getattr(self, "_picked", None)
        if picked is not None:
            return picked
        # Fall back to scanning + picking newest. Path used by callers
        # that bypass ``prepare`` (e.g. older tests, direct unit use).
        return self._recent()[0]

    def infer_name(self, raw_input, ctx: NewContext) -> str | None:
        try:
            picked = self._pick()
        except ValueError:
            return None
        return picked.stem or picked.name

    def plan(
        self,
        raw_input,
        name: str,
        options: NewOptions,
        ctx: NewContext,
    ) -> NewPlan:
        picked = self._pick()
        final_name = resolve_final_name(
            ctx.base_dir,
            name,
            add_date_prefix=options.timestamp,
            add_tmp_suffix=options.tmp,
            ts_name=options.ts_name,
            alpha_name=options.alpha_name,
        )
        target = ctx.base_dir / final_name
        steps = [
            f"mkdir {target}",
            f"move {picked} -> {target / picked.name}",
            f"write {target}/.base.yaml",
        ]
        if options.tags:
            steps.append(f"set tags {list(options.tags)}")
        return NewPlan(
            source_key=self.key,
            name=final_name,
            target=target,
            steps=steps,
            tags=list(options.tags),
            template=options.template,
            post_commands=list(options.post),
            log_kind="creation",
            log_payload={
                "kind": "downloaded",
                "source": str(picked),
                "filename": picked.name,
            },
            input=raw_input,
            open_shell=options.open,
        )

    def apply(self, plan: NewPlan, ctx: NewContext) -> NewResult:
        target = plan.target
        if target.exists():
            raise ValueError(f"target already exists: {target}")
        src = Path(plan.log_payload["source"])
        if not src.is_file():
            raise ValueError(f"source file vanished: {src}")
        target.mkdir(parents=True)
        try:
            shutil.move(str(src), str(target / src.name))
            ensure_base_marker(target)
            if plan.tags:
                clean = sorted({t.strip() for t in plan.tags if t.strip()})
                if clean:
                    save_base_tags(ctx.base_dir, target, clean)
            append_base_log(target, plan.log_kind, plan.log_payload)
        except (OSError, ValueError):
            shutil.rmtree(target, ignore_errors=True)
            raise
        cache_upsert_project_fast(ctx.base_dir, target)
        return NewResult(target=target, open_shell=plan.open_shell)
