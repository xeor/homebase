from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from ...cache.api import cache_load_rows
from ...core.constants import (
    ACTION_ACCEPT,
    ACTION_CANCEL,
    ARCHIVE_DIR_NAME,
    COLLISION_RED_RAMP,
    CURSOR_BG_HEX,
    CURSOR_FG_HEX,
)
from ...workspace.new.adapters import adapter_for_host, parse_url
from ...workspace.new.cmd import autodetect_source_key
from ...workspace.new.config_loader import NewConfigError, load_new_sources
from ...workspace.new.detect import classify_input
from ...workspace.new.name import resolve_final_name
from ...workspace.new.registry import builtin_keys, get_source_class
from ...workspace.new.sources.download import resolve_download_url
from ...workspace.new.sources.git import detect_git_url
from ...workspace.projects import discover_copier_templates
from ...workspace.rows import archive_destination, collect_workspace_rows
from .tag_plan import TagPlanScreen

# Same style as the hotbar's currently-selected cell — see
# ui/query/runtime.py:_CURSOR_STYLE.
_SELECTION_STYLE = f"{CURSOR_FG_HEX} on {CURSOR_BG_HEX}"


@dataclass
class _ToggleSpec:
    key: str            # NewOptions field name
    label: str          # what the user sees
    default: bool
    help: str


_TOGGLES: tuple[_ToggleSpec, ...] = (
    _ToggleSpec(
        "tmp", ".tmp suffix", False,
        "Append .tmp to the folder name (signals throwaway / WIP).",
    ),
    _ToggleSpec(
        "timestamp", "YYYY-MM-DD_ prefix", False,
        "Prefix the folder name with today's date (year-month-day, ISO).",
    ),
    _ToggleSpec(
        "cd", "open shell after create", True,
        "Spawn a shell inside the new project after creation.",
    ),
    _ToggleSpec(
        "archive", "send to _archive/", False,
        "Land the project in _archive/<year>/ instead of the active workspace.",
    ),
    _ToggleSpec(
        "ts_name", "use YYYYMMDD-HHMMSS as name", False,
        "Use a timestamp as the project name when no name is provided.",
    ),
    _ToggleSpec(
        "alpha_name", "use next a/b/c/... as name", False,
        "Use the next free alphabetic name (a, b, c, …, aa, …) when no name is provided.",
    ),
)

# Layout: toggles render column-major into Statics, each capped at
# _MAX_TOGGLE_ROWS rows. The number of columns adjusts to the toggle
# count so the block never grows beyond the bounded height.
_MAX_TOGGLE_ROWS = 4
_TOGGLE_COL_COUNT = max(
    1, (len(_TOGGLES) + _MAX_TOGGLE_ROWS - 1) // _MAX_TOGGLE_ROWS
)


_SOURCE_HELP: dict[str, str] = {
    "auto": "Auto-detect source from the input shape (URL / path / bare name).",
    "empty": "Create an empty project directory.",
    "local": "Move an existing local directory into the workspace.",
    "git": "Clone from a git URL into <name>/repo/.",
    "download": "Download a file or archive from a URL.",
    "downloaded": "Pick the newest file from the downloads dir.",
}


_SECTION_HELP: dict[int, str] = {
    0: "Project input — URL, path, or bare name. Source is auto-detected from the shape.",
    1: "Name override — optional. Leave blank to let the source infer the name.",
    2: "Source — pick the creation mode. 'auto' uses the auto-detected one.",
    # 3 (toggles) is rendered per-toggle from _TOGGLES.help
    4: "Tags — space/enter opens the tag picker.",
    # 5 (template) is rendered per-template below
}


class NewProjectScreen(ModalScreen[dict[str, object] | None]):
    """Generic form for `b new`. Returns a dict the caller marshals
    into an argparse Namespace for `plan_and_apply_one`."""

    CSS = """
    Screen {
        align: center middle;
    }
    #new_title { height: 1; padding: 0 1; }
    #new_top { height: 3; margin: 0 0 1 0; }
    #new_top Input { width: 1fr; }
    #new_left Static { height: auto; margin: 0 0 1 0; }
    #new_left #new_status_info {
        border-top: dashed $primary;
        padding: 1 0 0 0;
        margin: 1 0 0 0;
    }
    #new_right #new_matches_title { color: $warning; height: 1; }
    #new_right #new_status_matches { height: auto; }
    #new_right #new_help_title { color: $primary; height: 1; margin: 1 0 0 0; }
    #new_right #new_help { height: 1fr; }
    #new_name.auto-name > .input--placeholder { color: $warning; }
    #new_toggles_header { height: 1; margin: 0 0 0 0; }
    #new_toggles_wrap {
        height: auto;
        max-height: 4;
        margin: 0 0 1 0;
        overflow-y: auto;
    }
    #new_toggles_wrap > Static {
        width: 1fr;
        height: auto;
        margin: 0;
    }
    """
    BINDINGS = [
        Binding("tab", "next_section", "Next section", priority=True),
        Binding("shift+tab", "prev_section", "Previous section", priority=True),
        Binding("up", "move_up", "Up", priority=True),
        Binding("down", "move_down", "Down", priority=True),
        Binding("left", "move_left", "Left", priority=True),
        Binding("right", "move_right", "Right", priority=True),
        Binding("space", "toggle", "Toggle", priority=True),
        Binding("enter", ACTION_ACCEPT, "Create"),
        Binding("ctrl+q", ACTION_CANCEL, "Cancel"),
        Binding("escape", ACTION_CANCEL, "Cancel"),
    ]

    def __init__(self, base_dir_ref: Path, allow_stay_in_b: bool = True) -> None:
        super().__init__()
        self.base_dir_ref = base_dir_ref
        self.allow_stay_in_b = bool(allow_stay_in_b)
        self.templates = discover_copier_templates(base_dir_ref)
        try:
            self.sources_cfg = load_new_sources(base_dir_ref)
        except NewConfigError:
            self.sources_cfg = {}
        builtins = builtin_keys()
        children = sorted(
            k for k in self.sources_cfg.keys() if k not in set(builtins)
        )
        # `auto` lets the dispatcher pick based on input shape.
        self.source_choices: list[str] = ["auto", *builtins, *children]
        self.source_index = 0  # auto
        self.toggle_values: dict[str, bool] = {t.key: t.default for t in _TOGGLES}
        self.template_index = 0  # index into [None, *templates]
        self.selected_tags: set[str] = set()
        # Sections:
        #   0 = input, 1 = name, 2 = source, 3 = toggles,
        #   4 = tags (opens TagPlanScreen), 5 = template
        # The plan/status line at the bottom is not a tab stop —
        # enter from any section submits.
        self.focus_section = 0
        self.toggle_index = 0

    # ---------- compose ----------

    def compose(self) -> ComposeResult:
        with Vertical(id="new_project_box"):
            yield Static("[bold]Create new project[/]", id="new_title")
            with Horizontal(id="new_top"):
                yield Input(placeholder="URL / path / bare name", id="new_input")
                yield Input(placeholder="name (optional)", id="new_name")
            with Horizontal(id="new_body"):
                with Vertical(id="new_left"):
                    yield Static("", id="new_source_line")
                    yield Static("Options:", id="new_toggles_header")
                    with Horizontal(id="new_toggles_wrap"):
                        for col_idx in range(_TOGGLE_COL_COUNT):
                            yield Static("", id=f"new_toggles_col_{col_idx}")
                    yield Static("", id="new_tags_line")
                    yield Static("", id="new_template_line")
                    yield Static("", id="new_status_info")
                with Vertical(id="new_right"):
                    yield Static("[bold]Similar matches[/]", id="new_matches_title")
                    yield Static("", id="new_status_matches")
                    yield Static("[bold]Help[/]", id="new_help_title")
                    yield Static("", id="new_help")
            yield Static("", id="new_plan")
            yield Static(
                "tab/up-down section  left/right cycle  "
                "space toggle/edit  enter create  esc cancel",
                id="new_hotkeys",
            )

    def on_mount(self) -> None:
        self._set_section_focus()
        self._refresh()

    # ---------- helpers ----------

    def _set_section_focus(self) -> None:
        # We use `can_focus` rather than `disabled` because disabled
        # widgets reject all mouse events — and we want clicks on the
        # input boxes to route them back into the active section.
        # Priority bindings on the screen still absorb arrow/space/tab
        # keys before the focused Input would see them.
        inp = self.query_one("#new_input", Input)
        name = self.query_one("#new_name", Input)
        if self.focus_section == 0:
            inp.can_focus = True
            name.can_focus = True
            name.blur()
            inp.focus()
        elif self.focus_section == 1:
            inp.can_focus = True
            name.can_focus = True
            inp.blur()
            name.focus()
        else:
            inp.blur()
            name.blur()
            inp.can_focus = False
            name.can_focus = False
            self.set_focus(None)

    def _template_options(self) -> list[str | None]:
        return [None, *self.templates]

    def _current_template(self) -> str | None:
        opts = self._template_options()
        if not opts:
            return None
        self.template_index %= len(opts)
        return opts[self.template_index]

    def _current_source(self) -> str:
        if not self.source_choices:
            return "auto"
        self.source_index %= len(self.source_choices)
        return self.source_choices[self.source_index]

    def _input_value(self) -> str:
        return self.query_one("#new_input", Input).value.strip()

    def _name_value(self) -> str:
        return self.query_one("#new_name", Input).value.strip()

    def _tag_list(self) -> list[str]:
        return sorted(self.selected_tags)

    def _workspace_tag_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        active_rows, archived_rows, _ts = cache_load_rows(self.base_dir_ref)
        if not active_rows and not archived_rows:
            active_rows, archived_rows = collect_workspace_rows(
                self.base_dir_ref,
                include_git_dirty=False,
            )
        for row in active_rows + archived_rows:
            for tag in row.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return counts

    def _open_tag_picker(self) -> None:
        counts = self._workspace_tag_counts()
        all_tags = sorted(set(counts.keys()) | set(self.selected_tags))
        presence = {
            tag: ("all" if tag in self.selected_tags else "none")
            for tag in all_tags
        }
        self.app.push_screen(
            TagPlanScreen(
                all_tags,
                presence,
                counts,
                mode="add_only",
                base_dir=self.base_dir_ref,
            ),
            self._on_tag_picker_plan,
        )

    def _on_tag_picker_plan(self, plan: dict[str, str] | None) -> None:
        if plan is None:
            self._refresh()
            return
        updated: set[str] = set(self.selected_tags)
        for tag, op in plan.items():
            if op == "add":
                updated.add(tag)
            elif op == "remove":
                updated.discard(tag)
            # "keep" → no change
        self.selected_tags = updated
        self._refresh()

    def _detected_source(self) -> str:
        raw = self._input_value()
        if not raw:
            return "auto"
        # Use the same auto-detect the CLI dispatcher uses — URL
        # adapters, .git/SSH suffix probes, git.config.hosts, etc.
        # (so most URLs land on `download`, with `git` only when the
        # rules explicitly say so).
        return autodetect_source_key(raw, self.sources_cfg) or "auto"

    def _effective_source(self) -> str:
        sel = self._current_source()
        if sel == "auto":
            return self._detected_source()
        return sel

    def _has_name_candidate(self) -> bool:
        """True when a project name is already determined from the
        name override or inferred from the raw input. ``ts_name`` /
        ``alpha_name`` only apply when this is False."""
        if self._name_value():
            return True
        return bool(self._infer_name_for_preview(self._input_value()))

    def _resolved_name_preview(self) -> tuple[str, str]:
        """Return ``(resolved_name, marker)`` where marker is the explanation
        when the input can't yet be resolved. Mirrors the CLI's
        ``resolve_final_name`` exactly, so the preview honors ts_name /
        alpha_name / timestamp / tmp the same way the dispatcher will."""
        name_override = self._name_value()
        raw = self._input_value()
        candidate = name_override or self._infer_name_for_preview(raw)
        ts_name = self.toggle_values.get("ts_name", False)
        alpha_name = self.toggle_values.get("alpha_name", False)
        if not candidate and not (ts_name or alpha_name):
            return ("", "(awaiting name)")
        try:
            resolved = resolve_final_name(
                self.base_dir_ref,
                candidate,
                add_date_prefix=self.toggle_values["timestamp"],
                add_tmp_suffix=self.toggle_values["tmp"],
                ts_name=ts_name,
                alpha_name=alpha_name,
            )
        except ValueError as exc:
            return ("", f"invalid: {exc}")
        return (resolved, "")

    def _infer_name_for_preview(self, raw: str) -> str:
        """Mirror what the picked Source's ``infer_name`` would return,
        so the screen preview matches what's actually written to disk.

        For URLs that's the forge adapter's ``project_name`` (e.g. the
        gitea adapter strips the URL down to its repo name), falling
        back to the URL tail. For paths it's the directory's basename.
        For bare tokens it's the token itself.
        """
        if not raw:
            return ""
        shape = classify_input(raw)
        if shape == "bare":
            return raw
        if shape == "path":
            tail = raw.rstrip("/\\")
            return tail.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        # URL — defer to the host adapter when one applies, else fall
        # back to the URL tail. This is critical: a file URL on a
        # configured gitea host should preview the *repo* name (the
        # folder we'll actually create), not the file name.
        parsed = parse_url(raw)
        if parsed is not None:
            adapter = adapter_for_host(parsed.host, self._git_hosts_map())
            if adapter is not None:
                name = adapter.project_name(parsed)
                if name:
                    return name
        tail = raw.rstrip("/").rsplit("/", 1)[-1]
        if tail.endswith(".git"):
            tail = tail[:-4]
        return tail

    def _target_path(self, resolved: str) -> Path:
        """Where the project will actually land. With the archive
        toggle on, this is the same path the source's plan() would
        receive after ``apply_archive_modifier`` rewrites it —
        ``<base>/_archive/<year>/<YYYY-MM-DD>_<name>/``."""
        base_path = self.base_dir_ref / resolved
        if self.toggle_values.get("archive"):
            return archive_destination(base_path, self.base_dir_ref)
        return base_path

    def _similar_matches(self, query: str, limit: int = 5) -> list[tuple[str, int]]:
        q = query.strip().lower()
        if len(q) < 3:
            return []
        names: list[str] = []
        try:
            for p in self.base_dir_ref.iterdir():
                if not p.is_dir():
                    continue
                # Skip dotfiles AND any `_`-prefixed bookkeeping dir
                # (`_archive`, `_tags`, …) — those aren't real projects
                # and would never collide with a new project name.
                if p.name.startswith(".") or p.name.startswith("_"):
                    continue
                names.append(p.name)
        except OSError:
            return []
        scored: list[tuple[float, str]] = []
        for name in names:
            n = name.lower()
            ratio = difflib.SequenceMatcher(None, q, n).ratio()
            if q in n:
                ratio = max(ratio, 0.70)
            if n.startswith(q):
                ratio = max(ratio, 0.85)
            if n == q:
                ratio = 1.0
            if ratio >= 0.35:
                scored.append((ratio, name))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [(name, int(round(score * 100))) for score, name in scored[:limit]]

    # ---------- source resolution ----------

    def _resolve_base_key(self, key: str) -> str | None:
        """Walk parent chain until we hit a built-in source key.

        Mirrors the resolver in ``workspace/new/cmd.py`` but lives here
        to keep the screen free of that private helper."""
        builtins = set(builtin_keys())
        if key in builtins:
            return key
        walked: set[str] = set()
        cur = key
        while cur not in builtins:
            if cur in walked:
                return None  # cycle
            walked.add(cur)
            entry = self.sources_cfg.get(cur)
            if not isinstance(entry, dict):
                return None
            parent = entry.get("parent")
            if not isinstance(parent, str) or not parent:
                return None
            cur = parent
        return cur

    def _resolved_source_options(self, key: str) -> dict[str, object]:
        """Resolved default toggles for the given source key — class
        defaults overlaid with the user's config (including inherited
        overrides). Works for built-ins and custom child sources."""
        base = self._resolve_base_key(key)
        merged: dict[str, object] = {}
        if base:
            try:
                cls = get_source_class(base)
            except KeyError:
                cls = None
            if cls is not None:
                merged.update(cls.default_options)
        entry = self.sources_cfg.get(key) or {}
        for k, v in entry.items():
            if k in ("parent", "config"):
                continue
            merged[k] = v
        return merged

    def _resolved_source_config(self, key: str) -> dict[str, object]:
        """Resolved structural config dict for the source — class
        ``default_config`` overlaid with user config."""
        base = self._resolve_base_key(key)
        merged: dict[str, object] = {}
        if base:
            try:
                cls = get_source_class(base)
            except KeyError:
                cls = None
            if cls is not None:
                merged.update(cls.default_config)
        entry = self.sources_cfg.get(key) or {}
        user_cfg = entry.get("config")
        if isinstance(user_cfg, dict):
            merged.update(user_cfg)
        return merged

    # ---------- plan preview ----------

    def _git_hosts_map(self) -> dict[str, str]:
        """User-configured `git.config.hosts` mapping (host → adapter key)."""
        git_cfg = self.sources_cfg.get("git") or {}
        hosts = (git_cfg.get("config") or {}).get("hosts") or {}
        if not isinstance(hosts, dict):
            return {}
        return {str(k): str(v) for k, v in hosts.items()}

    def _url_adapter_name(self, raw: str) -> str | None:
        """Adapter key (e.g. 'github', 'gitlab') that matches the
        current input's host, or None if no adapter applies."""
        parsed = parse_url(raw)
        if parsed is None:
            return None
        adapter = adapter_for_host(parsed.host, self._git_hosts_map())
        return adapter.key if adapter is not None else None

    def _download_rewrites(self, source_key: str) -> list[dict[str, object]]:
        cfg = self._resolved_source_config(source_key)
        rewrites = cfg.get("url_rewrites") or []
        if not isinstance(rewrites, list):
            return []
        return [r for r in rewrites if isinstance(r, dict)]

    def _plan_steps_lines(self, eff_source: str, target: Path) -> list[str]:
        """Plan preview of what the source will do. URL adapters are
        consulted live (`detect_git_url` / `resolve_download_url`) so
        the user sees the actual clone / raw URL that will be used —
        not the raw input. No I/O is triggered (the downloaded source's
        FS scan is intentionally skipped here and rendered as a static
        description)."""
        raw = self._input_value()
        raw_display = raw or "<input>"
        steps: list[str] = []
        base = self._resolve_base_key(eff_source) or eff_source
        if base == "empty":
            steps.append(f"mkdir {target}")
            steps.append(f"write {target.name}/.base.yaml")
        elif base == "local":
            steps.append(f"move {raw_display} → {target}")
            steps.append(f"write {target.name}/.base.yaml")
        elif base == "git":
            hosts = self._git_hosts_map()
            clone_url = detect_git_url(raw, hosts) if raw else None
            adapter = self._url_adapter_name(raw) if raw else None
            steps.append(f"mkdir {target}")
            if clone_url and raw and clone_url != raw:
                steps.append(
                    f"git clone {clone_url} {target}/repo "
                    f"[dim](rewritten by {adapter or 'rule'})[/]"
                )
                steps.append(f"[dim]   raw input: {raw}[/]")
            elif clone_url:
                steps.append(f"git clone {clone_url} {target}/repo")
            else:
                steps.append(f"git clone {raw_display} {target}/repo")
                if raw:
                    steps.append("[dim red]   (no adapter rule matched — clones raw URL as-is)[/]")
            steps.append(f"write {target.name}/.base.yaml")
        elif base == "download":
            hosts = self._git_hosts_map()
            rewrites = self._download_rewrites(eff_source)
            fetch_url = (
                resolve_download_url(raw, hosts, rewrites) if raw else None
            )
            adapter = self._url_adapter_name(raw) if raw else None
            steps.append(f"mkdir {target}")
            if fetch_url and raw and fetch_url != raw:
                steps.append(
                    f"fetch {fetch_url} "
                    f"[dim](rewritten by {adapter or 'rule'})[/]"
                )
                steps.append(f"[dim]   raw input: {raw}[/]")
            else:
                steps.append(f"fetch {fetch_url or raw_display}")
            steps.append(f"write {target.name}/.base.yaml")
        elif base == "downloaded":
            cfg = self._resolved_source_config(eff_source)
            folder = cfg.get("folder", "~/Downloads")
            steps.append(f"mkdir {target}")
            steps.append(f"move newest file from {folder} → {target}/")
            steps.append(f"write {target.name}/.base.yaml")
        else:
            steps.append(f"create {target} via [bold]{eff_source}[/]")
        if self.selected_tags:
            steps.append(f"set tags {sorted(self.selected_tags)}")
        tmpl = self._current_template()
        if tmpl:
            steps.append(f"apply template {tmpl}")
        if self.toggle_values.get("archive"):
            steps.append(
                f"[dim](archive rewrite → lands under "
                f"{self.base_dir_ref / ARCHIVE_DIR_NAME}/<year>/<date>_<name>)[/]"
            )
        if self.toggle_values.get("cd"):
            steps.append("spawn shell in project")
        return steps

    def _template_details_text(self, key: str | None) -> str:
        """Multi-line template description for the help panel — pulls
        from the template's README.md (first paragraph), notes whether
        copier is used, and lists top-level contents."""
        if not key:
            return (
                "[bold cyan]template: (none)[/]\n"
                "Create the project without applying a copier template."
            )
        template_dir = (self.base_dir_ref / ".copier" / key).resolve()
        if not template_dir.is_dir():
            return (
                f"[bold cyan]template: {key}[/]\n"
                "[red](template directory missing)[/]"
            )
        lines: list[str] = [f"[bold cyan]template: {key}[/]"]
        readme = template_dir / "README.md"
        if readme.is_file():
            try:
                text = readme.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            description: list[str] = []
            for raw_line in text.splitlines():
                stripped = raw_line.strip()
                if not stripped:
                    if description:
                        break
                    continue
                if stripped.startswith("#"):
                    if description:
                        break
                    continue
                description.append(stripped)
                if len(description) >= 4:
                    break
            if description:
                lines.append(" ".join(description))
        uses_copier = (
            (template_dir / "copier.yml").is_file()
            or (template_dir / "copier.yaml").is_file()
        )
        if uses_copier:
            lines.append("")
            lines.append("[dim]uses copier — will prompt for variables[/]")
        try:
            entries = sorted(
                p.name for p in template_dir.iterdir()
                if not p.name.startswith(".")
            )
        except OSError:
            entries = []
        if entries:
            lines.append("")
            lines.append("[bold]Contents:[/]")
            for e in entries[:8]:
                lines.append(f"  - {e}")
            if len(entries) > 8:
                lines.append(f"  … +{len(entries) - 8} more")
        return "\n".join(lines)

    # ---------- help ----------

    def _source_details_text(self, key: str) -> str:
        """Multi-line source description used in the help panel when
        section 2 (source) is focused.

        Shows: title, help_short, default toggles (with origin), and
        structural config (e.g. downloaded.folder). Custom child
        sources are resolved through ``_resolve_base_key`` so the
        same view works for any user-defined entry."""
        if key == "auto":
            detected = self._detected_source()
            lines = [
                "[bold cyan]source: auto[/]",
                _SOURCE_HELP["auto"],
            ]
            if detected and detected != "auto":
                lines.append(f"[dim]→ would use [cyan]{detected}[/dim] for current input[/]")
            return "\n".join(lines)

        base = self._resolve_base_key(key)
        lines: list[str] = [f"[bold cyan]source: {key}[/]"]
        if base and base != key:
            lines.append(f"[dim](child of {base})[/]")
        try:
            cls = get_source_class(base) if base else None
        except KeyError:
            cls = None
        if cls is not None and cls.help_short:
            lines.append(cls.help_short)

        toggles = self._resolved_source_options(key)
        toggle_lines: list[str] = []
        for spec in _TOGGLES:
            if spec.key not in toggles and not (spec.key == "cd" and "open" in toggles):
                continue
            raw = toggles.get(spec.key)
            if spec.key == "cd" and raw is None:
                raw = toggles.get("open")
            mark = r"\[x]" if raw else r"\[ ]"
            toggle_lines.append(f"  {mark} {spec.label}")
        if toggle_lines:
            lines.append("")
            lines.append("[bold]Default toggles:[/]")
            lines.extend(toggle_lines)

        cfg = self._resolved_source_config(key)
        if cfg:
            lines.append("")
            lines.append("[bold]Config:[/]")
            for k, v in cfg.items():
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    def _help_text(self) -> str:
        sec = self.focus_section
        if sec == 2:
            return self._source_details_text(self._current_source())
        if sec == 3 and 0 <= self.toggle_index < len(_TOGGLES):
            spec = _TOGGLES[self.toggle_index]
            return f"[bold cyan]{spec.label}[/]\n{spec.help}"
        if sec == 5:
            return self._template_details_text(self._current_template())
        return _SECTION_HELP.get(sec, "")

    # ---------- refresh ----------

    def _refresh(self) -> None:
        # Name field — when the user hasn't typed an override we
        # display the auto-inferred name as an orange placeholder so
        # it's obvious which name will actually be used and that they
        # can override it.
        name_input = self.query_one("#new_name", Input)
        if self._name_value():
            name_input.placeholder = "name (optional)"
            name_input.remove_class("auto-name")
        else:
            inferred = self._infer_name_for_preview(self._input_value())
            if inferred:
                name_input.placeholder = f"auto: {inferred}"
                name_input.add_class("auto-name")
            else:
                name_input.placeholder = "name (optional)"
                name_input.remove_class("auto-name")

        # Source row.
        detected = self._detected_source()
        cursor = ">" if self.focus_section == 2 else " "
        sel = self._current_source()
        choices_str = "  ".join(
            f"[{_SELECTION_STYLE}] {c} [/]" if c == sel else f" {c} "
            for c in self.source_choices
        )
        self.query_one("#new_source_line", Static).update(
            f"{cursor} source (auto detected: [cyan]{detected}[/]):  {choices_str}"
        )

        # Toggles — split column-major across N Static columns so the
        # block has a bounded height. Brackets are escaped because Rich
        # would otherwise eat them as markup tags. ``ts_name`` /
        # ``alpha_name`` are auto-name generators that only kick in
        # when no name candidate is present; they're dimmed when a
        # name is already determined so the user can see they're
        # currently inert.
        has_name = self._has_name_candidate()
        for col_idx in range(_TOGGLE_COL_COUNT):
            start = col_idx * _MAX_TOGGLE_ROWS
            end = min(start + _MAX_TOGGLE_ROWS, len(_TOGGLES))
            col_lines: list[str] = []
            for global_idx in range(start, end):
                spec = _TOGGLES[global_idx]
                cur = (
                    ">"
                    if self.focus_section == 3 and global_idx == self.toggle_index
                    else " "
                )
                mark = r"\[x]" if self.toggle_values[spec.key] else r"\[ ]"
                inert = spec.key in {"ts_name", "alpha_name"} and has_name
                row = f"{cur} {mark} {spec.label}"
                if inert:
                    row = f"[dim]{row}[/]"
                col_lines.append(row)
            self.query_one(
                f"#new_toggles_col_{col_idx}", Static
            ).update("\n".join(col_lines))

        # Tags row.
        tag_cursor = ">" if self.focus_section == 4 else " "
        tag_summary = ", ".join(sorted(self.selected_tags)) or "-"
        tag_hint = (
            " [dim](space/enter to edit)[/]" if self.focus_section == 4 else ""
        )
        self.query_one("#new_tags_line", Static).update(
            f"{tag_cursor} tags:  {tag_summary}{tag_hint}"
        )

        # Template row.
        opts = self._template_options()
        opts_labels = []
        for idx, item in enumerate(opts):
            label = "(none)" if item is None else item
            if idx == self.template_index:
                opts_labels.append(f"[{_SELECTION_STYLE}] {label} [/]")
            else:
                opts_labels.append(f" {label} ")
        tcursor = ">" if self.focus_section == 5 else " "
        self.query_one("#new_template_line", Static).update(
            f"{tcursor} template: {' '.join(opts_labels)}"
        )

        # Status panels (left = key:value info, right = similar matches).
        resolved, marker = self._resolved_name_preview()
        target = self._target_path(resolved) if resolved else None
        info_lines: list[str] = []
        if marker:
            info_lines.append(f"[dim]{marker}[/]")
        elif target is not None:
            exists_marker = (
                "[bold red]YES[/]" if target.exists() else "[bold green]no[/]"
            )
            info_lines.extend(
                [
                    f"[bold green]name[/]: {resolved}",
                    f"[bold green]path[/]: [dim]{target}[/]",
                    f"[bold green]exists[/]: {exists_marker}",
                ]
            )
        eff_source = self._effective_source()
        info_lines.append(f"[bold green]source[/]: {eff_source}")
        tags = self._tag_list()
        info_lines.append(
            f"[bold green]tags[/]: {', '.join(tags) if tags else '-'}"
        )
        tmpl = self._current_template()
        info_lines.append(f"[bold green]template[/]: {tmpl or '-'}")
        toggles_on = [s.label for s in _TOGGLES if self.toggle_values[s.key]]
        info_lines.append(
            f"[bold green]options[/]: {', '.join(toggles_on) if toggles_on else '-'}"
        )
        if target is not None and resolved:
            steps = self._plan_steps_lines(eff_source, target)
            if steps:
                info_lines.append("")
                info_lines.append("[bold green]plan[/]:")
                for step in steps:
                    info_lines.append(f"  - {step}")
        self.query_one("#new_status_info", Static).update("\n".join(info_lines))

        # Similar-name suggestions.
        suggestions = self._similar_matches(resolved) if resolved else []
        if suggestions:
            match_lines: list[str] = []
            for item, pct in suggestions:
                bucket = max(0, min(len(COLLISION_RED_RAMP) - 1, (100 - pct) // 10))
                style = COLLISION_RED_RAMP[bucket]
                match_lines.append(f"[{style}]- {item} ({pct}%)[/]")
            match_text = "\n".join(match_lines)
        elif not resolved:
            match_text = "[dim](type a name to see collisions)[/]"
        else:
            match_text = "[dim](no similar names in workspace)[/]"
        self.query_one("#new_status_matches", Static).update(match_text)

        # Help panel (context-sensitive — follows the keyboard cursor).
        self.query_one("#new_help", Static).update(self._help_text())

        # Plan line — status only, not a tab stop.
        if not resolved or target is None:
            plan_text = "Waiting for name…"
        elif target.exists():
            plan_text = f"[bold yellow]Will open existing[/] {resolved}"
        else:
            plan_text = (
                f"Will create [bold green]{resolved}[/] using "
                f"[bold cyan]{eff_source}[/]"
            )
        self.query_one("#new_plan", Static).update(plan_text)

    # ---------- input events ----------

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in {"new_input", "new_name"}:
            self._refresh()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id in {"new_input", "new_name"}:
            self.action_accept()

    # ---------- mouse ----------

    _SECTION_FOR_ID: dict[str, int] = {
        "new_input": 0,
        "new_name": 1,
        "new_source_line": 2,
        "new_toggles_header": 3,
        "new_tags_line": 4,
        "new_template_line": 5,
    }

    def on_click(self, event: events.Click) -> None:
        """Clicking a form row focuses that section. For a toggle
        column (multi-line Static), the click row + column resolves
        to the individual toggle the user pointed at."""
        widget = event.widget
        if widget is None:
            return
        wid = getattr(widget, "id", None) or ""
        if wid.startswith("new_toggles_col_"):
            try:
                col_idx = int(wid.rsplit("_", 1)[-1])
            except ValueError:
                return
            self.focus_section = 3
            line = max(0, event.y)
            candidate = col_idx * _MAX_TOGGLE_ROWS + line
            if 0 <= candidate < len(_TOGGLES):
                self.toggle_index = candidate
            self._set_section_focus()
            self._refresh()
            return
        section = self._SECTION_FOR_ID.get(wid)
        if section is None:
            return
        self.focus_section = section
        self._set_section_focus()
        self._refresh()

    # ---------- navigation ----------

    def _section_count(self) -> int:
        return 6  # 0..5

    def action_next_section(self) -> None:
        self.focus_section = (self.focus_section + 1) % self._section_count()
        self._set_section_focus()
        self._refresh()

    def action_prev_section(self) -> None:
        self.focus_section = (self.focus_section - 1) % self._section_count()
        self._set_section_focus()
        self._refresh()

    def action_move_left(self) -> None:
        if self.focus_section == 2 and self.source_choices:
            self.source_index = (self.source_index - 1) % len(self.source_choices)
        elif self.focus_section == 3:
            # Jump to the same row in the previous toggle column.
            new_idx = self.toggle_index - _MAX_TOGGLE_ROWS
            if 0 <= new_idx < len(_TOGGLES):
                self.toggle_index = new_idx
        elif self.focus_section == 5:
            opts = self._template_options()
            if opts:
                self.template_index = (self.template_index - 1) % len(opts)
        self._refresh()

    def action_move_right(self) -> None:
        if self.focus_section == 2 and self.source_choices:
            self.source_index = (self.source_index + 1) % len(self.source_choices)
        elif self.focus_section == 3:
            new_idx = self.toggle_index + _MAX_TOGGLE_ROWS
            if 0 <= new_idx < len(_TOGGLES):
                self.toggle_index = new_idx
        elif self.focus_section == 5:
            opts = self._template_options()
            if opts:
                self.template_index = (self.template_index + 1) % len(opts)
        self._refresh()

    def action_move_up(self) -> None:
        # Inside the toggle grid, up navigates within the current
        # column. At the column top, fall through to the previous
        # section.
        if self.focus_section == 3:
            row = self.toggle_index % _MAX_TOGGLE_ROWS
            if row > 0:
                self.toggle_index -= 1
                self._refresh()
                return
        self.action_prev_section()

    def action_move_down(self) -> None:
        if self.focus_section == 3:
            row = self.toggle_index % _MAX_TOGGLE_ROWS
            if row < _MAX_TOGGLE_ROWS - 1 and self.toggle_index + 1 < len(_TOGGLES):
                self.toggle_index += 1
                self._refresh()
                return
        self.action_next_section()

    def action_toggle(self) -> None:
        if self.focus_section == 3:
            spec = _TOGGLES[self.toggle_index]
            self.toggle_values[spec.key] = not self.toggle_values[spec.key]
            self._refresh()
            return
        if self.focus_section == 4:
            self._open_tag_picker()
            return
        # In source / template sections, space cycles forward.
        if self.focus_section in {2, 5}:
            self.action_move_right()
            return

    # ---------- accept / cancel ----------

    def action_accept(self) -> None:
        resolved, marker = self._resolved_name_preview()
        plan_widget = self.query_one("#new_plan", Static)
        if marker and "invalid" in marker:
            plan_widget.update(f"[red]{marker}[/]")
            return
        if not resolved and not self._input_value():
            plan_widget.update("[red]input or name required[/]")
            return

        payload: dict[str, object] = {
            "input": self._input_value(),
            "name": self._name_value(),
            "source": self._current_source(),  # "auto" or specific key
            "tmp": self.toggle_values["tmp"],
            "timestamp": self.toggle_values["timestamp"],
            "cd": self.toggle_values["cd"],
            "archive": self.toggle_values["archive"],
            "ts_name": self.toggle_values.get("ts_name", False),
            "alpha_name": self.toggle_values.get("alpha_name", False),
            "template": self._current_template() or "",
            "tags": self._tag_list(),
            # confirm/yes are CLI-only — yes=True is forced in the
            # bridge because the user already confirmed by hitting
            # Enter on the form.
            "after_create": "open" if self.allow_stay_in_b is False else (
                "open" if self.toggle_values["cd"] else "stay"
            ),
        }
        self.dismiss(payload)

    def action_cancel(self) -> None:
        self.dismiss(None)
