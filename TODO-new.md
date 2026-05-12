# `b new` — unified project creation

Goal: collapse `b new`, `b migrate`, and `b c` into a single `b new` that
auto-detects the input type, supports a name override, exposes today's
quick-create behaviors (`--tmp`, `--timestamp`, …) as CLI flags, drives
the interactive TUI from the same code path, and is trivially extensible
with new input handlers (Sources) — including user-defined child Sources
that change only the defaults.

---

## 1. Current state (everything below disappears)

- `b new` (parser.py:19, dispatch.py:58 → `workspace/projects.py:cmd_new`):
  launches the TUI with `start_new=True`. Interactive flow only.
- `b migrate [--archive] <path>...` (parser.py:54, dispatch.py:87 →
  `commands/archive.py:cmd_migrate` → `commands/workspace.py:cmd_migrate`):
  moves existing directories into `~/base/`, creates `.base.yaml`, appends
  `migration` log entry, syncs tag symlinks. `--archive` moves into
  `_archive/<year>/` with a `YYYY-MM-DD_<name>` prefix
  (`archive/ops.py:archive_destination`).
- `b c <key>` (parser.py:26, `workspace/projects.py:cmd_create_quick`):
  templated quick-create with options `prefix-datetime`, `suffix-tmp`,
  `changedir`, `prompt-name`, `generate-ts-name`,
  `generate-next-alpha-name`, plus optional copier template.

**All three commands are removed.** `b new` (alias `b n`) replaces them.
Every option that lived in `b c` template config becomes a `b new` CLI
flag. Existing keybindings/hotbar entries that call `b c …` must be
rewritten to `b new …` (sweep at the end of the work — see §10).

---

## 2. New surface

```
b new [<input>] [<name>] [mode-flag] [options...]
b n   ...
```

- `<input>`  optional. Path, URL, or bare name. With `--multi`,
              one or more inputs.
- `<name>`   optional. Override for the final folder name under `~/base/`.
              Disallowed with `--multi` or `--ask-name`.

**Mode flags** (mutually exclusive — force a Source, bypass auto-detect):

| Flag           | Source            |
|----------------|-------------------|
| `--empty`      | EmptySource       |
| `--local`      | LocalDirSource    |
| `--git`        | GitSource         |
| `--download`   | DownloadSource    |
| `--downloaded` | DownloadedSource  |

Plus `--as <child-key>` to pick a registered child Source (see §5).
`--as` is mutually exclusive with the table above.

**Common flags** (combine freely with any Source):

- `--archive`                      send the result into
                                   `~/base/_archive/<year>/<YYYY-MM-DD>_<name>/`
                                   instead of `~/base/<name>/`. Works
                                   with every Source.
- `--tag <tag>` (repeatable)       initial tags written to `.base.yaml`.
- `--template <key>`               copier/scaffold template under
                                   `<base>/.copier/<key>`. Applies to any
                                   Source — for git it fills `<name>/`
                                   alongside `<name>/repo/`.
- `--open` / `--no-open`           spawn shell on success. Per-Source
                                   default (see §7).
- `--cd` / `--no-cd`               alias pair for `--open`/`--no-open`
                                   (matches today's `changedir`).
- `--tmp` / `--no-tmp`             toggle `.tmp` suffix.
- `--timestamp` / `--no-timestamp` toggle `YYYY-DD-MM_` date prefix.
- `--ts-name`                      use `YYYYMMDD-HHMMSS` as the name when
                                   none is provided.
- `--alpha-name`                   use next free `a`, `b`, …, `aa`.
- `--ask-name`                     prompt interactively for the name.
                                   Mutually exclusive with `<name>`
                                   positional. Works inside `--multi` —
                                   prompts per item. Other name options
                                   (`--tmp`, `--timestamp`, …) still
                                   apply to the answer.
- `--ask-source`                   force "which Source?" prompt instead
                                   of auto-detecting. Useful with
                                   `--multi` where each item may be a
                                   different type.
- `--confirm` / `--no-confirm`     summarize and ask before applying.
                                   Default off, **except** for
                                   DownloadedSource which defaults on.
- `--post <cmd>` (repeatable)      post-creation shell commands run in
                                   the project dir (reuses
                                   `run_post_commands`).
- `--yes`                          skip any confirm prompt (overrides
                                   `--confirm`).
- `--dry-run`                      print the resolved plan, no fs writes.
- `--multi`                        accept multiple `<input>`s. Each is
                                   auto-detected independently and can
                                   resolve to a different Source. The
                                   `<name>` positional is disallowed;
                                   use `--ask-name` if you need per-item
                                   names.

All Boolean flags use `argparse.BooleanOptionalAction` so each has its
own `--no-…` counterpart, and the parser default is `None` — the option
resolver (§4) uses `None` to mean "fall through to Source / config
default".

No args, TTY → opens the interactive TUI flow described in §11. Same
modal as ctrl-n inside `b`. No args, non-TTY → fail fast with today's
"b new requires an interactive terminal" message.

---

## 3. Auto-detect

Input shape rules (first match wins; mode flag bypasses; `--ask-source`
forces an interactive choice):

1. **URL** (`scheme://…` or `git@host:…`):
   - URL adapter matches → adapter says clone or download (§8).
   - else: `.git` suffix anywhere → GitSource.
   - else: → DownloadSource.
2. **Path-shaped input** — contains `/` or `\`, starts with `./`, `../`,
   `/`, `~`, or ends with `/`. → LocalDirSource. If the directory
   doesn't exist → hard fail. **No filesystem probing on bare tokens.**
3. **Bare token** (no path separators, no scheme) → EmptySource. The
   value becomes the project name. Existence of a same-named dir in
   cwd is irrelevant.
4. **No `<input>`** → TUI new-project flow (§11).

The old "guess if a folder with that name exists in cwd" behavior goes
away. Migrate must be expressed as a path (`./thing` or `thing/`) or
via `--local thing`.

---

## 4. Options & defaults model

Each Source entry in config has two flavours of data:

- **option keys** (top-level) — Boolean/scalar toggles that map 1:1 to
  CLI flags (`tmp`, `timestamp`, `cd`/`open`, `confirm`, `tags`,
  `template`, …). These are CLI-overridable.
- **`config:` sub-key** — Source-specific structural settings that have
  no CLI counterpart (e.g. `download.config.url_rewrites`,
  `git.config.git_hosts`, `downloaded.config.folder`). Not CLI-
  overridable; they shape what the Source can do, not per-invocation
  behavior.

Resolution layers, each overrides the previous:

1. **Source defaults** — class attributes `default_options` and
   `default_config` on the Source. e.g. DownloadedSource sets
   `default_options = {"tmp": True, "timestamp": True, "cd": True,
   "confirm": True}` and `default_config = {"folder": "~/Downloads"}`.
2. **User config** — `.homebase/config.yaml` (existing global config,
   no new file), under a new top-level `new:` key. Only one subkey:
   `sources:`. **No project-level config.**

   ```yaml
   new:
     sources:
       empty:                       # known key → override defaults
         tmp: false
         cd: true

       git:
         cd: true
         config:
           # host → forge-type map. Forge-type names a registered URL
           # adapter (github, gitlab, bitbucket, codeberg, gitea,
           # sourcehut, …) that knows the URL conventions: clone URL
           # shape, blob→raw rewrite, repo-name extraction. Used by
           # GitSource (detect clone target from a bare URL) and
           # DownloadSource (rewrite blob→raw). Supersedes the old
           # flat "git_hosts" list — that gave a host but no way to
           # know how to rewrite its URLs.
           hosts:
             git.mycompany.com: gitlab
             code.example.org:  gitea
             git.example.com/scm: bitbucket

       download:
         config:
           # Generic regex fallback for non-forge URLs (internal wikis,
           # CMS exports, …). Runs only if no forge adapter matched.
           url_rewrites:
             - match: "^https://internal\\.example\\.com/wiki/(.+)$"
               rewrite: "https://internal.example.com/wiki/raw/\\1"

       downloaded:
         config:
           folder: ~/Downloads      # picked-up file lives here

       scratch:                     # unknown key → must set `parent:`
         parent: empty              # …or `b` fails on startup
         tmp: true
         timestamp: true
         cd: true

       prj:
         parent: empty
         template: python-uv
         tags: [work]
   ```
   Rules:
   - Key matches a built-in Source key → overrides that Source's
     defaults (options) and/or `config:` block.
   - Unknown key → must declare `parent: <key>` pointing at another
     registered source (built-in or child). Missing `parent:` is a
     startup config error.
   - Children inherit options **and** `config:` from the parent
     transitively. Overrides merge shallowly per top-level option key
     and deep-merge inside `config:`.

3. **CLI flags** — explicit `--tmp` / `--no-tmp` etc. always win for
   option keys. `config:` is never touched by the CLI.

Resolution lives in `workspace/new/options.py:resolve(source,
child_key, cli_ns, cfg)`. Returns a frozen pair: `NewOptions`
(consumed by `Source.plan()`) and `NewConfig` (consumed at Source
construction).

Python escape hatch: advanced users can subclass any Source and
register it programmatically (see §5). Config covers the common case;
Python covers anything that needs custom logic in `infer_name`,
`detects`, `plan`, or `apply`.

Resolved: deep-merge for `config:`, shallow-merge for option keys.
Children re-state only what differs from the parent.

Resolved: Source `config:` is never touched by the CLI. Anything that
ought to be CLI-toggleable is an option key, not a `config:` key.

Resolved: the kitchen-sink example lives in the existing
`docs/kitchen-sink-config.md` (replacing the current `create_templates:`
block). Every option, every `config:` key, and at least one example
of every Source + child pattern must appear there so it's the
canonical reference.

---

## 5. Provider architecture

```
workspace/new/
├── __init__.py        # public entry: cmd_new(ns, base_dir, cwd)
├── base.py            # Source ABC, NewPlan, NewResult, NewOptions
├── registry.py        # Source + child registration; loads `new.sources`
├── detect.py          # shape detection → Source (when no mode-flag)
├── options.py         # 3-layer option resolution
├── name.py            # name resolution (apply tmp/timestamp/etc.)
├── prompt.py          # --ask-name / --ask-source / --confirm helpers
├── sources/
│   ├── __init__.py
│   ├── empty.py
│   ├── local.py
│   ├── git.py
│   ├── download.py
│   └── downloaded.py
├── adapters/          # URL adapters (§8)
│   ├── __init__.py
│   ├── base.py
│   ├── github.py
│   ├── gitlab.py
│   ├── bitbucket.py
│   ├── codeberg.py
│   └── srht.py
├── hints.py           # apply `new.hints` URL rewrites + extra git hosts
└── archive_mod.py     # post-plan transform for --archive
```

`base.Source` (ABC):

```python
class Source(ABC):
    key: ClassVar[str]                          # "empty", "git", ...
    default_options: ClassVar[dict[str, Any]] = {}
    help_short: ClassVar[str] = ""              # for --help / completion
    supports_multi: ClassVar[bool] = True       # every Source supports
                                                # --multi by default

    @abstractmethod
    def detects(self, input: str | None, ctx: NewContext) -> bool: ...

    @abstractmethod
    def infer_name(self, input: str | None, ctx: NewContext) -> str | None:
        """Pure: derive a default project name from the input/context."""

    @abstractmethod
    def plan(self, input: str | None, name: str,
             options: NewOptions, ctx: NewContext) -> NewPlan: ...

    @abstractmethod
    def apply(self, plan: NewPlan, ctx: NewContext) -> NewResult: ...
```

`NewPlan` is pure data (target dir, action steps, post commands, signals
shown to user). `apply()` is the only side-effecting step.

**Child Sources** — two equivalent paths:

- **Config**: entry under `new.sources` with `parent: <key>`. The registry
  synthesizes a thin wrapper around the parent Source with merged
  defaults. No Python needed.
- **Python**: subclass + `@register_source`. Useful when you need to
  override `detects` / `infer_name` / `plan`.

Both reach `b new --as <key>` and both appear in `b new --help` and
shell completion.

**`--archive` is NOT a Source.** It's a post-`plan()` modifier that
rewrites the target dir under `_archive/<year>/<YYYY-MM-DD>_<name>/`
and changes the log entry kind. Applies after any Source.

---

## 6. Shared helpers (reuse, no new I/O primitives)

- `resolve_new_project_name(...)`                    `workspace/projects.py`
- `_next_available_alpha_name(...)`                  `workspace/projects.py`
- `discover_copier_templates(base_dir)`              `workspace/projects.py`
- `create_project(...)`                              `workspace/projects.py`
- `run_post_commands(target, commands)`              `workspace/projects.py`
- `ensure_base_marker(target)`                       `metadata/api.py`
- `save_base_tags(base_dir, target, tags)`           `metadata/api.py`
- `append_base_log(target, kind, payload)`           `metadata/api.py`
- `sync_tag_symlinks(base_dir)`                      `metadata/api.py`
- `cache_upsert_project_fast(base_dir, target)`      `cache/api.py`
- `open_shell_in_dir(target)`                        `tmux/flow.py`
- `archive_destination(src, base_dir)`               `workspace/rows.py`
- `_run_textual_ui(...)` with `start_new=True`       `ui/`

---

## 7. Per-Source behavior

Every Source declares `default_options`, an `infer_name()`, and supports
`--multi` (the dispatcher just calls `plan`+`apply` per item).

### 7.1 EmptySource (`key="empty"`)
- Detects: bare token (no separators, no scheme).
- `infer_name(input)`: the input itself.
- Defaults: `{}`.
- Plan: `~/base/<name>/`.
- Apply: `mkdir` → marker → tags → optional template → log
  `"creation"` → cache upsert → optional shell open.

### 7.2 LocalDirSource (`key="local"`)
- Detects: path-shaped input.
- `infer_name(path)`: `path.name` (after trailing-slash strip).
- Defaults: `{}`.
- Plan: `shutil.move(<input>, ~/base/<name>)`. Refuses if `<input>` is
  already under `~/base/`.
- Apply: move → marker → tags → log `"migration"` → sync tag symlinks
  → cache upsert → optional shell open.

### 7.3 GitSource (`key="git"`)
- Detects: URL adapter says "clone", `.git` suffix anywhere, or SSH form
  `git@host:owner/repo[.git]`. **No clone-side whitelist.**
- `infer_name(url)`: last URL path segment, `.git` stripped.
- Defaults: `{}`.
- Layout: `~/base/<name>/` is the project root (marker lives here);
  clone goes into `~/base/<name>/repo/`.
- Plan: mkdir parent → `git clone <url> repo` (cwd=parent) → marker →
  tags → optional template applied to the parent dir → log `"creation"`
  with `{"source": url, "kind": "git-clone"}` → cache upsert.
- Failure: a failed clone rolls back the parent dir before any marker
  is written.

### 7.4 DownloadSource (`key="download"`)
- Detects: URL that isn't git (adapter says download, or no `.git` /
  SSH form), or explicit `--download`.
- `infer_name(url)`: adapter override (e.g. github raw → repo name)
  → URL basename without extension → URL host.
- Defaults: `{}`.
- Plan: mkdir `~/base/<name>/`, fetch the URL into it. One file per
  invocation. Filename = `Content-Disposition` → URL path tail →
  `download`.
- Apply: mkdir → fetch (stdlib `urllib.request`, no extra deps) →
  marker → tags → log `"creation"` with `{"source": url,
  "kind": "download", "filename": "..."}` → cache upsert.
- Adapter URL rewrites apply (e.g. github `/blob/<ref>/<path>` →
  `raw.githubusercontent.com/.../refs/heads/<ref>/<path>`).
- **No archive auto-extraction.** Drop the file; user runs `tar xf`.

### 7.5 DownloadedSource (`key="downloaded"`)
- Detects: `--downloaded` only (no positional input).
- `infer_name(_)`: basename (without extension) of the most-recently-
  modified file in the configured folder.
- Defaults (options): `{"tmp": True, "timestamp": True, "cd": True,
  "confirm": True}`.
- Defaults (config): `{"folder": "~/Downloads"}`.
- Configurable in `.homebase/config.yaml`:
  ```yaml
  new:
    sources:
      downloaded:
        config:
          folder: ~/Downloads
  ```
- Plan: mkdir `~/base/<name>/`, move the picked file into it.
- Apply: mkdir → move → marker → tags → log `"creation"` with
  `{"source": "<orig path>", "kind": "downloaded"}` → cache upsert →
  shell open (default on).
- `--confirm` is on by default here; summary shows source path, target
  dir, options, and post commands before any fs write.

### 7.6 `--archive` modifier (cross-cutting)
- Applied after `plan()`. Rewrites target dir to
  `~/base/_archive/<year>/<YYYY-MM-DD>_<name>/` via the existing
  `archive_destination(...)` (today's format, date-only prefix; no
  full ISO timestamp).
- Log entry kind becomes `"migration"` with
  `{"archive": True, "signals": [...]}`.
- Works with every Source. Archiving a `DownloadedSource` result is
  allowed — it just lands directly in `_archive/...`.

Resolved: same-day-same-name collisions fall through to the existing
destination-exists error. User picks a different `<name>` and re-runs
(closed in §13).

---

## 8. URL adapters + per-Source extension config

Adapters live in `workspace/new/adapters/`. Each adapter encodes the
URL conventions of one forge family (github, gitlab, bitbucket,
codeberg/gitea, sourcehut, …). Built-in adapters auto-register on the
canonical public host **and** by forge-type key:

| Adapter key   | Built-in host  | clone form                            | download rewrite                                       |
|---------------|----------------|---------------------------------------|--------------------------------------------------------|
| `github`      | github.com     | `/{o}/{r}` or `/{o}/{r}/tree/{ref}`   | `/{o}/{r}/blob/{ref}/{p}` → raw.githubusercontent.com  |
| `gitlab`      | gitlab.com     | `/{o}/{r}` or `/{o}/{r}/-/tree/{ref}` | `/{o}/{r}/-/blob/{ref}/{p}` → `/-/raw/{ref}/{p}`       |
| `bitbucket`   | bitbucket.org  | `/{o}/{r}` or `/{o}/{r}/src/{ref}`    | `/{o}/{r}/src/{ref}/{p}` → `/raw/{ref}/{p}`            |
| `gitea`       | (no host)      | `/{o}/{r}`                            | `/{o}/{r}/src/branch/{ref}/{p}` → `/raw/branch/{...}`  |
| `codeberg`    | codeberg.org   | (gitea-shape — alias for `gitea`)     | (gitea-shape)                                          |
| `sourcehut`   | git.sr.ht      | `/~{u}/{r}`                           | n/a                                                    |

```python
class UrlAdapter(ABC):
    key: ClassVar[str]                  # "github", "gitlab", ...
    canonical_hosts: ClassVar[list[str]] = []   # built-in host bindings

    @abstractmethod
    def to_clone_url(self, parsed: ParseResult) -> str | None: ...
    def to_download_url(self, parsed: ParseResult) -> str | None: ...
    def project_name(self, parsed: ParseResult) -> str | None: ...
```

**Host → forge-type binding** lives under `git.config.hosts` in
`.homebase/config.yaml`. There is **no separate `new.hints`
namespace**. Both GitSource and DownloadSource read this map (via the
registry); it's the single source of truth for "this host behaves like
forge X":

```yaml
new:
  sources:
    git:
      config:
        hosts:
          git.mycompany.com:   gitlab    # self-hosted GitLab
          code.example.org:    gitea     # gitea/forgejo install
          git.example.com/scm: bitbucket # bitbucket server under /scm
    download:
      config:
        url_rewrites:                     # regex fallback for non-forge URLs
          - match: "^https://internal\\.example\\.com/wiki/(.+)$"
            rewrite: "https://internal.example.com/wiki/raw/\\1"
```

URL resolution order:

1. Look up `host[+path-prefix]` in the merged map of built-in canonical
   hosts + `git.config.hosts` → adapter key → adapter.
2. Adapter's `to_clone_url` / `to_download_url` decides git vs download
   and produces the resolved URL.
3. If no adapter matched and the URL has `.git` / SSH form →
   GitSource clones as-is.
4. Otherwise → DownloadSource. Before fetching, apply
   `download.config.url_rewrites` (regex, first match wins).
5. Adapter / rewrite misses fetch the URL untouched.

Self-hosted instances with sub-path routing (e.g. `git.example.com/scm`)
match the longest `host[+path-prefix]` prefix in the map.

No project-local config.

**Decision (was §12.3)**: clones are triggered by `.git` suffix, SSH
form, or an adapter match (either canonical host or
`git.config.hosts`). Everything else downloads. No further heuristics.

Cross-Source coupling: DownloadSource asks the registry for GitSource's
resolved `hosts` map when classifying a URL. The registry exposes a
`resolved_config(source_key)` accessor for this; Sources never reach
into each other's modules directly.

---

## 9. UX contract

```
$ b new
  → opens the interactive new-project flow (same as ctrl-n in b)

$ b new myproj
  → ~/base/myproj/                  (EmptySource)

$ b new ./some-dir
  → moves ./some-dir → ~/base/some-dir/   (LocalDirSource)

$ b new ./some-dir myproj
  → moves ./some-dir → ~/base/myproj/

$ b new some/path/                          # trailing slash → path
  → moves some/path/ → ~/base/path/

$ b new https://github.com/foo/bar
  → mkdir ~/base/bar/; git clone … ~/base/bar/repo   (GitSource)

$ b new https://github.com/foo/bar.git aprj
  → mkdir ~/base/aprj/; git clone … ~/base/aprj/repo

$ b new git@github.com:foo/bar.git
  → name = bar, same layout

$ b new https://github.com/foo/bar/blob/main/TODO.md
  → mkdir ~/base/TODO/; fetch raw URL into it
    (DownloadSource + github adapter rewrite)

$ b new https://example.com/blob.iso
  → mkdir ~/base/blob/; fetch into it          (DownloadSource, no
                                                adapter)

$ b new --downloaded
  → confirm prompt, then move newest ~/Downloads file into
    ~/base/2026-12-05_<basename>.tmp/         (defaults: tmp+timestamp
                                                +cd+confirm)

$ b new path/to/dir myproj --tag wip --no-open
  → migrate with tag, no shell spawn

$ b new --archive ./old-thing
  → ~/base/_archive/2026/2026-12-05_old-thing
                                              (--archive on LocalDir)

$ b new https://github.com/foo/bar --archive
  → clones into ~/base/_archive/2026/2026-12-05_bar/repo

$ b new --as scratch
  → uses the `scratch` child-Source from .homebase/config.yaml

$ b new --dry-run https://github.com/foo/bar
  → prints resolved Source, target, post-actions; touches nothing

$ b new --multi ./a ./b ./c
  → three LocalDir migrations

$ b new --multi ./a https://github.com/x/y bare-name
  → mixed: 1 LocalDir, 1 Git, 1 Empty

$ b new --multi ./a https://github.com/x/y bare-name --ask-source
  → asks per item which Source to use (defaulting to the detected one)

$ b new --multi ./a ./b --ask-name
  → asks per item what to name it (other options like --tmp still
    decorate the answer)
```

**Conflict policy**: if the resolved target already exists, fail with a
plain info line _plus_ context to help decide whether it's the same
project:

```
target already exists: ~/base/myproj
  type:        directory
  has marker:  yes (.base.yaml)
  created:     2025-08-14 (mtime 2026-04-30)
  size:        12 MB / 87 files
  git branch:  main (clean)
  tags:        [work, llm]
```

Source picks which fields are meaningful (Git shows branch+dirty,
Download shows file size, etc.). Reuses `git_info`, `project_row` data
where possible. No rename, no automatic retry — user picks a different
`<name>` and re-runs.

**Default open behavior**: per-Source default, overridable by
`--open`/`--no-open` (= `--cd`/`--no-cd`). Empty/Local/Git/Download
default to no-open; Downloaded defaults to open.

`--confirm` (off by default, on for DownloadedSource): prints the full
resolved plan and waits for `y/N`. `--yes` skips it. `--dry-run`
prints the plan and exits without confirming or applying.

---

## 10. Parser / dispatch wiring + sweep

- parser.py — replace `b new` with the full surface:
  ```python
  p_new = sub.add_parser("new", help="create a new project")
  p_new.add_argument("inputs", nargs="*", default=[])  # supports --multi
  # post-parse: split inputs/name (1 input + 1 name; or n inputs w/ --multi)
  mode = p_new.add_mutually_exclusive_group()
  for key in ("empty", "local", "git", "download", "downloaded"):
      mode.add_argument(f"--{key}", dest="mode", action="store_const",
                        const=key)
  mode.add_argument("--as", dest="child_key", default=None)
  p_new.add_argument("--archive", action="store_true")
  p_new.add_argument("--tag", action="append", default=[])
  p_new.add_argument("--template", default="")
  p_new.add_argument("--tmp",       action=BooleanOptionalAction, default=None)
  p_new.add_argument("--timestamp", action=BooleanOptionalAction, default=None)
  p_new.add_argument("--open",      action=BooleanOptionalAction, default=None)
  p_new.add_argument("--cd",        action=BooleanOptionalAction, default=None)
  p_new.add_argument("--confirm",   action=BooleanOptionalAction, default=None)
  p_new.add_argument("--ts-name",   action="store_true")
  p_new.add_argument("--alpha-name", action="store_true")
  p_new.add_argument("--ask-name", action="store_true")
  p_new.add_argument("--ask-source", action="store_true")
  p_new.add_argument("--post", action="append", default=[])
  p_new.add_argument("--yes", action="store_true")
  p_new.add_argument("--dry-run", action="store_true")
  p_new.add_argument("--multi", action="store_true")
  ```
  Every flag carries `help=...`. `b new --help` is the canonical
  reference. A separate `b help new` topic dumps the registered
  Sources/children with their resolved defaults.

- `n` alias: `sub.add_parser("n", parents=[p_new], add_help=False)`.

- **Remove** `migrate`, `c`, and the legacy `new` branch from parser,
  dispatch, completion, and the suppression set in
  `cli/entry.py:323/330`.

- dispatch.py: one branch — `workspace.new.cmd_new(ns, base_dir, cwd)`.

- `cli/completion.py`: **dynamic** completion for everything under
  `b new` / `b n`:
  - drop `c`, `migrate` from `_TOP_LEVEL_COMMANDS`; add `n`.
  - register a callback in `_subcommand_candidates("new" | "n", …)`
    that reads from the live registry: every mode flag, every common
    flag, every registered child-source key after `--as`, every
    copier template after `--template`, every Source key after
    `--ask-source` follow-ups, etc. Completion data is generated from
    the same metadata used by `--help`.
  - Extending Sources/options must not require editing
    `completion.py`.

- **Keybinding / hotbar sweep**: grep config + docs for `b c`,
  `b migrate`, and `b new` invocations and rewrite them to the new
  surface. The TUI uses the new code path directly (§11), so this is
  only about external invocations.

Resolved: `create_templates:` is removed from the config schema
entirely (closed in §13.3). `docs/kitchen-sink-config.md` shows how
every old template option maps onto `new.sources` entries.

---

## 11. TUI new-project flow

`ui/screens/new_project.py:NewProjectScreen` becomes a generic form
driven by the same registry as the CLI — no code duplication.

- Single text input for `<input>` (URL, path, or bare name). Live
  feedback area below it shows the auto-detected Source key (or
  "ambiguous" / "would fail" with a reason).
- Override dropdown for the Source (mirrors the mode-flag table).
- Optional name input.
- Toggle row generated **dynamically** from `NewOptions` schema:
  every Boolean option (`tmp`, `timestamp`, `open`/`cd`, `confirm`,
  `archive`) renders as a switch initially set to the resolved
  default for the current Source. Changing the Source updates the
  defaults.
- Tag entry + template dropdown.
- Submit runs the exact same `cmd_new(...)` pipeline the CLI calls.
  No bespoke "new project" code path in the TUI.
- ctrl-n inside `b` (the table view) opens this screen; `b new` with
  no input also opens it. Identical implementation.

`b new --multi` is not exposed in the TUI in v1 — the modal handles
one item at a time. Power-user multi stays CLI-only.

**Form layout** (single row of two text inputs at the top):

```
┌──────────────────────────────────────┬─────────────────────┐
│  input (URL / path / bare name)      │  name (optional)    │
└──────────────────────────────────────┴─────────────────────┘
  detected: <SourceKey>   override: [ empty | local | git | … ]
  [ ] tmp   [ ] timestamp   [ ] cd   [ ] confirm   [ ] archive
  tags: ___________________   template: [ … ]
  [ Submit ]   [ Cancel ]
```

The name box is optional; empty → Source's `infer_name()` runs.

**Interactivity rules** for prompts launched from the CLI:

- `--ask-name` / `--ask-source` are **invalid when `b new` is invoked
  from inside the running TUI** (would cause nested prompts). They
  raise a config-style error if the dispatcher detects the TUI is
  already active.
- From a plain CLI with a TTY: use stdlib `input()` (no Textual). The
  Textual modal is reserved for the no-arg case.
- Non-TTY: hard fail with "requires an interactive terminal".

Resolved: `b` doesn't keep itself alive alongside spawned shells, so
this edge case isn't real. The rule is simply: ctrl-n → modal → no
`--ask-*` prompts.

---

## 12. Tests

`tests/test_new_*.py`:

- `tests/test_new_detect.py` — shape detection table: URL, SSH form,
  `.git`, github blob URL, gitlab/bitbucket/codeberg variants, `./x`,
  `x/`, `/abs`, `~/x`, bare token, no-input, mode-flag overrides,
  `git.config.hosts` entry routing a bare self-hosted URL through the
  matching forge adapter (clone + blob→raw).
- `tests/test_new_options.py` — three-layer resolution: Source defaults
  vs child defaults vs CLI; `--no-tmp` overriding a child's `tmp: true`;
  child with missing `parent:` is rejected at config load.
- `tests/test_new_name.py` — per-Source `infer_name`; `--tmp` /
  `--timestamp` / `--ts-name` / `--alpha-name` combinations; explicit
  `<name>` always wins; conflict prints the contextual info from §9.
- `tests/test_new_empty.py` — marker + tags + log + cache upsert;
  conflict path emits contextual info.
- `tests/test_new_local.py` — move into base; refuses src already under
  base; `--multi` runs N moves; `--multi` rejects a positional name.
- `tests/test_new_git.py` — local bare repo as URL (no network);
  `<name>/repo` layout; marker at `<name>/`; failed clone rolls back.
- `tests/test_new_download.py` — `http.server` fixture; file lands
  inside project dir; marker exists; log records URL.
- `tests/test_new_downloaded.py` — fixture sets `downloads_dir`;
  newest file picked; default tmp+timestamp+confirm applied;
  `--yes` bypasses confirm.
- `tests/test_new_archive.py` — `--archive` works with empty, local,
  git, download, downloaded; format matches today's
  `YYYY-MM-DD_<name>`.
- `tests/test_new_adapters.py` — github/gitlab/bitbucket/codeberg
  clone + raw rewrites.
- `tests/test_new_hosts.py` — `git.config.hosts` binds a self-hosted
  host to a forge adapter (gitea/gitlab/bitbucket) and both Sources
  use it (clone URL + blob→raw rewrite). Longest-prefix wins for
  hosts with sub-paths. `download.config.url_rewrites` regex fallback
  fires only when no adapter matched.
- `tests/test_new_ask.py` — `--ask-name` works alone and inside
  `--multi`; `--ask-source` overrides detection; both honor `--yes`
  in non-interactive mode (fail loud).
- `tests/test_new_cli.py` — argparse round-trips for every documented
  invocation; mode flags mutually exclusive; `--dry-run` writes
  nothing; `<name>` rejected with `--multi`/`--ask-name`.
- `tests/test_new_tui.py` — `NewProjectScreen` renders the options
  generated from the registry, switches default values when the
  Source changes, and submits through `cmd_new(...)`.
- `tests/test_new_completion.py` — completion for `b new` reflects
  the live registry: adding a child Source in the test config makes
  it appear after `--as`.
- `tests/test_new_legacy_config.py` — a `create_templates:` block in
  the global config is rejected at load with the pointer to
  `docs/kitchen-sink-config.md`.

All tests use `tmp_path`. No fs/sqlite mocks (AGENTS.md §9).

---

## 13. Resolved decisions / out-of-scope

### 13.1 Archive same-day-same-name collisions — RESOLVED
Fail with today's "destination exists" error. No auto-suffix. User
passes a different `<name>`.

### 13.2 `--ask-name` / `--ask-source` in non-TTY — RESOLVED
Hard fail with "requires an interactive terminal". Also invalid when
called from inside the running TUI (see §11).

### 13.3 Old `b c` / `create_templates` config — RESOLVED
Removed entirely. `docs/kitchen-sink-config.md` (the existing
kitchen-sink) replaces the `create_templates:` block with the full
`new.sources` shape, including a `tmp` child that matches today's
`prefix-datetime + suffix-tmp + generate-ts-name + tags:[scratch]`
template. Config loader rejects a `create_templates:` block with a
clear "use `new.sources` (see docs/kitchen-sink-config.md)" error.

### 13.4 `--multi` with mode flag — RESOLVED
The mode flag applies to every item. Items that don't fit the forced
Source are reported per-item with a clear error and **skipped**; the
batch continues with the remaining items. Final exit code is non-zero
if any item failed/skipped.

Resolved: per-item failures print + skip, the batch continues with the
remaining items, exit code is non-zero if any item failed.

### 13.5 `b a` and `b fix`
Out of scope. Leave alone; file a follow-up if you want them folded
into `b new` too.

---

## 14. Status

All CLAUDE_COMMENT items resolved:

- §4 deep-merge / shallow-merge → confirmed.
- §4 `config:` not CLI-overridable → confirmed.
- §4 kitchen-sink lives in existing `docs/kitchen-sink-config.md`
  (replacing the current `create_templates:` block).
- §8 forge-host map: `git.config.hosts` is a `host → forge-type` map.
  Adapters auto-register on canonical hosts plus a forge-type key;
  self-hosted entries reuse the same adapter logic via the user-
  supplied forge type. DownloadSource reads the map via the registry.
- §8 gitea key: `gitea` adapter has no built-in canonical host
  (`codeberg.org` is bound separately). Self-hosted gitea/forgejo
  installs must be declared in `git.config.hosts` — `b` has no way
  to sniff the forge type from a bare URL.
- §11 TUI / `--ask-*` resolved; no shell-pane edge case.
- §13.4 multi-mode failures: per-item skip, batch continues, non-zero
  exit if any item failed.

No open questions. Plan is ready to implement.