# `b new` — unified project creation

Goal: collapse `b new` and `b migrate` into a single `b new` that auto-detects
the input type, supports a name override, exposes today's quick-create
behaviors (`--tmp`, `--timestamp`, …) as flags, and is trivially extensible
with new input handlers (Sources) — including user-defined child Sources
that change only the defaults.

---

## 1. Current state

- `b new` (parser.py:19, dispatch.py:58 → `workspace/projects.py:cmd_new`):
  launches the TUI with `start_new=True`. Interactive flow only.
- `b migrate [--archive] <path>...` (parser.py:54, dispatch.py:87 →
  `commands/archive.py:cmd_migrate` → `commands/workspace.py:cmd_migrate`):
  moves existing directories into `~/base/`, creates `.base.yaml`, appends
  `migration` log entry, syncs tag symlinks. Optional archive mode moves
  into `_archive/<year>/` with timestamped name.
- `b c <key>` (parser.py:26, `workspace/projects.py:cmd_create_quick`):
  templated quick-create with options `prefix-datetime`, `suffix-tmp`,
  `changedir`, `prompt-name`, `generate-ts-name`, `generate-next-alpha-name`,
  and optional copier template. **The new system must reuse this machinery
  rather than duplicate it.**
COMMENT: The "b new" command will replace this. These options needs to be parameters. I want "b c" command removed

`b migrate` disappears entirely. `b new` becomes the umbrella. `b c` stays
for now but should share the same Source/options layer underneath (see
open question §12.1).
COMMENT: "b c" will be removed as all functionality will go into "b new"

---

## 2. New surface

```
b new [<input>] [<name>] [mode-flag] [options...]
b n   ...
```

- `<input>`  optional. Path, URL, or bare name.
- `<name>`   optional. Override for the final folder name under `~/base/`.

**Mode flags** (mutually exclusive — force a Source, bypass auto-detect):

| Flag           | Source            |
|----------------|-------------------|
| `--empty`      | EmptySource       |
| `--local`      | LocalDirSource    |
| `--git`        | GitSource         |
| `--download`   | DownloadSource    |
| `--downloaded` | DownloadedSource  |

Plus `--as <child-key>` to pick a registered child Source (see §5).
`--as` is also mutually exclusive with the table above.

**Common flags** (combine freely with any Source):

- `--archive`                      send the result into `_archive/<year>/`
                                   with timestamped name (today's
                                   `b migrate --archive` behavior, but
                                   works with any Source).
- `--tag <tag>` (repeatable)       initial tags written to `.base.yaml`.
- `--template <key>`               copier/scaffold template under
                                   `<base>/.copier/<key>`. Applies to any
                                   Source — for git this fills `<name>/`
                                   alongside `<name>/repo/`.
- `--no-open` / `--open`           override the Source's default "spawn
                                   shell on success" behavior.
- `--cd` / `--no-cd`               alias pair for the above (matches
                                   `changedir` in today's `b c`).
- `--tmp` / `--no-tmp`             toggle `.tmp` suffix on the folder name.
- `--timestamp` / `--no-timestamp` toggle `YYYY-DD-MM_` date prefix.
- `--ts-name`                      use `YYYYMMDD-HHMMSS` as the name when
                                   none provided.
- `--alpha-name`                   use the next free `a`, `b`, …, `aa`
                                   name when none provided.
- `--prompt-name`                  prompt interactively for the name.
- `--post <cmd>` (repeatable)      post-creation shell commands, run in
                                   the project dir (reuses
                                   `run_post_commands`).
- `--yes`                          skip confirm prompts.
- `--dry-run`                      print the resolved plan, no fs writes.
- `--multi`                        accept multiple `<input>`s; disables
                                   the `<name>` positional (see §12.2).

All Boolean flags use `argparse.BooleanOptionalAction` so each one has
its own `--no-…` counterpart. Default for each option is **resolved
from the Source**, not the parser — see §4.

No args → interactive flow; opens the same modal that ctrl-n already
opens inside the TUI (`ui/screens/new_project.py:NewProjectScreen`).
Not a separate code path — see §7.6.

---

## 3. Auto-detect

Input shape rules (first match wins; mode flag overrides):

1. **URL** (`scheme://…` or `git@host:…`):
   - URL adapter matches → adapter decides git vs download (§8).
   - else: `.git` suffix anywhere → git clone.
   - else: → download.
2. **Path-shaped input** — input contains `/` or `\`, starts with `./`,
   `../`, `/`, `~`, or ends with `/`. Always LocalDirSource. If the
   directory doesn't exist → hard fail. **No filesystem probing on
   bare tokens.**
3. **Bare token** (no path separators, no scheme) → EmptySource. The
   value becomes the project name. Existence of a sibling directory
   under cwd is irrelevant; we never guess.
4. **No `<input>`** → TUI new-project modal.

This is a deliberate simplification: today's "if a folder with that name
exists in cwd, migrate it" guess goes away. Migrate must be expressed
as a path (`./thing` or `thing/`), or via `--local thing`.

---

## 4. Options & defaults model

Options come from three layers, each overriding the previous:

1. **Source defaults** — class attribute `default_options: dict[str, Any]`
   on the Source. e.g. `DownloadedSource` sets
   `{"tmp": True, "timestamp": True, "cd": True}`.
2. **Config (optional)** — `<base>/.config/new.yaml` may set defaults
   per Source key or per `--as` child key (mirrors today's
   `create_templates` for `b c`). Shape:
   ```yaml
   sources:
     empty:    { tmp: false, cd: true }
     git:      { cd: true }
   children:
     scratch:  { parent: empty, tmp: true, timestamp: true, cd: true }
     prj:      { parent: empty, template: python-uv, tags: [work] }
   ```
COMMENT: Yes, but this should be configured in .homebase/config.yaml (the normal config file). Under the "new" top key. "sources" should be the only key needed. If one exists, like "empty" and "git" like in this example, it should change the default option. If it doesnt exists, like "scratch" and "prj", it should require a "parent" set (or b should fail).
COMMENT: Make also sure that for advance usecases, this should be easy to extend in python as well with class inheritence.

3. **CLI flags** — explicit `--tmp` / `--no-tmp` always win.

Resolution lives in `workspace/new/options.py:resolve_options(source,
child_key, cli_ns)`. Returns a frozen `NewOptions` dataclass consumed by
`Source.plan()`.

Negation is uniform: every Boolean option has `--<name>` and `--no-<name>`
(via `BooleanOptionalAction`), and parser default is `None` so the resolver
can tell "user didn't set it" from "user set it false".

---

## 5. Provider architecture

```
workspace/new/
├── __init__.py        # public entry: cmd_new(ns, base_dir, cwd)
├── base.py            # Source ABC, NewPlan, NewResult, NewOptions
├── registry.py        # Source registration + child-source resolution
├── detect.py          # shape detection → Source (without mode-flag)
├── options.py         # 3-layer option resolution
├── name.py            # name inference + validation + collision check
├── sources/
│   ├── __init__.py
│   ├── empty.py       # EmptySource
│   ├── local.py       # LocalDirSource
│   ├── git.py         # GitSource
│   ├── download.py    # DownloadSource
│   ├── downloaded.py  # DownloadedSource
│   └── interactive.py # opens NewProjectScreen via run_textual_ui
├── adapters/          # URL adapters (§8)
│   ├── __init__.py
│   ├── base.py        # UrlAdapter ABC
│   ├── github.py
│   ├── gitlab.py
│   ├── bitbucket.py
│   ├── codeberg.py
│   └── srht.py
└── archive_mod.py     # post-plan transform for --archive
```

`base.Source` (ABC, not Protocol — we want inheritable behavior):

```python
class Source(ABC):
    key: ClassVar[str]                 # "empty", "git", ...
    default_options: ClassVar[dict[str, Any]] = {}
    help_short: ClassVar[str] = ""     # for --help

    @abstractmethod
    def detects(self, input: str | None) -> bool: ...

    @abstractmethod
    def plan(self, input: str | None, name: str | None,
             options: NewOptions, ctx: NewContext) -> NewPlan: ...

    @abstractmethod
    def apply(self, plan: NewPlan, ctx: NewContext) -> NewResult: ...
```

`NewPlan` is pure data (target dir, action steps, post_commands, signals
shown to user). `apply()` is the only side-effecting step.

**Child Sources** — registered via the registry, not subclasses on disk
unless behavior differs. Two ways to define one:

- Python: subclass + register. `class ScratchSource(EmptySource): key =
  "scratch"; default_options = {"tmp": True, "timestamp": True}`.
- Config: `children:` block in `new.yaml` (see §4). The registry
  synthesizes a thin wrapper around the parent Source with merged
  defaults. No Python required for the common case.

Both reach `b new --as <key>`. Both show up in `b new --help` and shell
completion.

**`--archive` is NOT a Source.** It's a post-`plan()` transform applied
by the dispatcher: rewrites the target dir under `_archive/<year>/<ts>_<name>/`
and rewires the log entry. Works with empty, local, git, download.
Implementation in `archive_mod.py:apply_archive(plan, ctx)`.

---

## 6. Shared helpers (reuse, no new I/O primitives)

- `resolve_new_project_name(...)`                    `workspace/projects.py`
- `_next_available_alpha_name(...)`                  `workspace/projects.py`
- `discover_copier_templates(base_dir)`              `workspace/projects.py`
- `create_project(...)` (template + marker + tags)   `workspace/projects.py`
- `run_post_commands(target, commands)`              `workspace/projects.py`
- `ensure_base_marker(target)`                       `metadata/api.py`
- `save_base_tags(base_dir, target, tags)`           `metadata/api.py`
- `append_base_log(target, "creation"|"migration", payload)`
                                                     `metadata/api.py`
- `sync_tag_symlinks(base_dir)`                      `metadata/api.py`
- `cache_upsert_project_fast(base_dir, target)`      `cache/api.py`
- `open_shell_in_dir(target)`                        `tmux/flow.py`
- `archive_destination(src, base_dir)`               `workspace/rows.py`
                                                     (for `--archive`)
- `_run_textual_ui(...)` with `start_new=True`       `ui/`
                                                     (for `b new` no-arg)

---

## 7. Per-Source behavior

### 7.1 EmptySource (`key="empty"`)
- Detect: bare token, not URL-shaped.
- Defaults: `{}` (nothing on).
- Plan: `~/base/<name>/` (after name resolution + options).
- Apply: `mkdir`, `ensure_base_marker`, write tags, optional template,
  `append_base_log("creation", {...})`, cache upsert, optional shell open.

### 7.2 LocalDirSource (`key="local"`)
- Detect: path-shaped input.
- Defaults: `{}`.
- Plan: `shutil.move(<input>, ~/base/<name>)`; refuse if `<input>` is
  already under `~/base/`.
- Apply: move, marker, log `"migration"`, sync tag symlinks, cache
  upsert.
- Multi-mode: with `--multi`, accept N inputs, run N plans, no `<name>`
  positional allowed.

### 7.3 GitSource (`key="git"`)
- Detect: URL adapter says "this is a clone URL", OR `.git` suffix
  anywhere in the URL, OR `git@host:owner/repo[.git]` SSH form,
  OR explicit `--git`. **No host whitelist for the clone itself — any
  URL that looks like git is cloned.**
- Defaults: `{}`.
- Layout: `~/base/<name>/` is the project root, `.base.yaml` lives there;
  the actual clone goes into `~/base/<name>/repo/`.
- Plan steps: mkdir parent → `git clone <url> repo` (cwd=parent) →
  marker → tags → optional template applied to parent (alongside
  `repo/`) → log `"creation"` with `{"source": url, "kind": "git-clone"}`.
- Failure: a failed clone rolls back the parent dir before any marker
  is written.
- Name inference: last URL path segment with `.git` stripped.

### 7.4 DownloadSource (`key="download"`)
- Detect: URL that isn't git (adapter says download, or no `.git` and
  no SSH form), OR explicit `--download`.
- Defaults: `{}`.
- Plan: mkdir `~/base/<name>/`, fetch the URL into that directory
  (filename from `Content-Disposition` or URL path tail; falls back to
  `download`). One file per invocation.
- Apply: mkdir → fetch (stdlib `urllib.request`, no extra deps) →
  marker → tags → log `"creation"` with `{"source": url,
  "kind": "download", "filename": "..."}`.
- Name inference: URL adapter override (e.g. github raw → repo name),
  else the URL's basename without extension, else the host.
- Adapter URL rewrites apply here (github `/blob/<ref>/<path>` →
  `https://raw.githubusercontent.com/<owner>/<repo>/refs/heads/<ref>/<path>`).
- Out of scope for v1: auto-extract `.tar.gz`/`.zip` (§12.4).

### 7.5 DownloadedSource (`key="downloaded"`)
- Detect: `--downloaded` only (no positional input).
- Defaults: `{"tmp": True, "timestamp": True, "cd": True}`.
- Plan: pick the most-recently-modified regular file under `~/Downloads`
  (path configurable in `new.yaml`), name = file basename minus
  extension; target `~/base/<name>/` (after applying name options).
- Apply: mkdir → move the file into the new dir → marker → tags → log
  `"creation"` with `{"source": "<orig path>", "kind": "downloaded"}`.
COMMENT: Path should be configurable in the default .homebase/config.yaml, under "new".
COMMENT: We need an additional "--confirm" option that sums up what it wants to do and asks for confirmation. This option should be default on DownloadedSource

### 7.6 Interactive (no Source — opens the existing TUI modal)
- Trigger: `b new` with no input and no mode flag.
- Behavior: identical to ctrl-n inside the TUI. Calls `run_textual_ui(
  base_dir, cwd, start_new=True)` which opens
  `ui/screens/new_project.py:NewProjectScreen`. Same modal, same
  post-actions. No duplicate flow.
- Non-TTY: fail fast with today's error message
  ("b new requires an interactive terminal").

### 7.7 `--archive` modifier (cross-cutting)
- Applied after the Source produces a plan. Rewrites:
  - target dir from `~/base/<name>/` to
    `~/base/_archive/<year>/<ts>_<name>/` (via `archive_destination`).
  - log entry kind from `"creation"` to `"migration"` with
    `{"archive": True, "signals": [...]}`.
- Compatible with every Source. Archiving a `DownloadedSource` result
  is allowed — it just lands in `_archive/...` directly.

---

## 8. URL adapters

Per-host classes in `workspace/new/adapters/`. **Not** a security
whitelist — they exist to map "human" URLs to the right action and to
rewrite blob/raw URLs:

```python
class UrlAdapter(ABC):
    @abstractmethod
    def matches(self, parsed: ParseResult) -> bool: ...
    def to_clone_url(self, parsed: ParseResult) -> str | None: ...   # None = not a clone
    def to_download_url(self, parsed: ParseResult) -> str | None: ... # None = not a download
    def project_name(self, parsed: ParseResult) -> str | None: ...
```

Built-in adapters:

| Host           | clone form                              | download rewrite                                        |
|----------------|-----------------------------------------|---------------------------------------------------------|
| github.com     | `/{o}/{r}` or `/{o}/{r}/tree/{ref}`     | `/{o}/{r}/blob/{ref}/{path}` → raw.githubusercontent.com|
| gitlab.com     | `/{o}/{r}` or `/{o}/{r}/-/tree/{ref}`   | `/{o}/{r}/-/blob/{ref}/{path}` → `/-/raw/{ref}/{path}`  |
| bitbucket.org  | `/{o}/{r}` or `/{o}/{r}/src/{ref}`      | `/{o}/{r}/src/{ref}/{path}` → `/raw/{ref}/{path}`       |
| codeberg.org   | (mirrors gitea)                         | `/{o}/{r}/src/branch/{ref}/{path}` → `/raw/branch/...`  |
| git.sr.ht      | `/~{u}/{r}`                             | n/a in v1                                               |
| (self-hosted)  | adapter list is open — add more here    |                                                         |

**No whitelist on clones.** If no adapter matches but the URL has `.git`
or is SSH form, GitSource still clones. Self-hosted GitLab works out of
the box on `--git <url>` even without a dedicated adapter; an adapter
just adds smart bare-URL detection and blob-rewrites. Adding one is a
single file under `adapters/` + register call.

For DownloadSource with no adapter match: fetch the URL as-is.

COMMENT: There should be a configuration option under "new.hints", where I can put hints for the adapters. Like adding a domain I know is gitlab. Or add a url transform (regex), to the downloadable version of it.

---

## 9. UX contract

```
$ b new
  → opens the same modal as ctrl-n inside b

$ b new myproj
  → ~/base/myproj/                  (EmptySource, bare token)

$ b new ./some-dir
  → moves ./some-dir → ~/base/some-dir/   (LocalDirSource)

$ b new ./some-dir myproj
  → moves ./some-dir → ~/base/myproj/

$ b new some/path/                          # trailing slash → path
  → moves some/path/ → ~/base/path/         (LocalDirSource)

$ b new https://github.com/foo/bar
  → mkdir ~/base/bar/; git clone … ~/base/bar/repo   (GitSource)

$ b new https://github.com/foo/bar.git aprj
  → mkdir ~/base/aprj/; git clone … ~/base/aprj/repo

$ b new git@github.com:foo/bar.git
  → name = bar, same layout

$ b new https://github.com/foo/bar/blob/main/TODO.md
  → mkdir ~/base/TODO/; fetch raw URL into it   (DownloadSource +
                                                 adapter rewrite)

$ b new https://example.com/blob.iso
  → mkdir ~/base/blob/; fetch into it           (DownloadSource, no
                                                 adapter)

$ b new --downloaded
  → moves the most-recent ~/Downloads file into
    ~/base/2026-12-05_<basename>.tmp/          (defaults add tmp+timestamp)

$ b new path/to/dir myproj --tag wip --no-open
  → migrate with tag, no shell spawn

$ b new --archive ./old-thing
  → ~/base/_archive/2026/2026-12-05T14-22-01+0100_old-thing
                                              (--archive on LocalDir)
COMMENT: The dateformat is wrong, it should be ~/base/_archive/2026/2026-12-05_old-thing

$ b new https://github.com/foo/bar --archive
  → clones into ~/base/_archive/2026/<ts>_bar/repo   (--archive on Git)

$ b new --as scratch
  → uses the `scratch` child-Source from new.yaml

$ b new --dry-run https://github.com/foo/bar
  → prints resolved Source, target, post-actions; touches nothing

$ b new --multi ./a ./b ./c
  → three LocalDir migrations; no name positional accepted
```

**Conflict policy**: if the resolved target already exists, fail with a
plain info message (`target already exists: <path>`). No rename, no
suggestion.
COMMENT: Also add some additional info about the destination that already exists. Give me some context so I can know if it is the same or not as the one I'm already trying to do

**Default open behavior**: matches today's `b c` — Source default,
overridable by `--open`/`--no-open` / `--cd`/`--no-cd`. Empty/Git default
to no-open; DownloadedSource defaults to open (because the user is
actively unpacking something they just got).

`--dry-run` prints: resolved Source key, child key (if any), input,
final name, target dir, planned steps, post commands. No fs writes.

---

## 10. Parser / dispatch wiring

- parser.py:19 — replace `sub.add_parser("new")` with the full surface:
  ```python
  p_new = sub.add_parser("new", help="create a new project")
  p_new.add_argument("input", nargs="?", default=None)
  p_new.add_argument("name",  nargs="?", default=None)
  mode = p_new.add_mutually_exclusive_group()
  for key in ("empty", "local", "git", "download", "downloaded"):
      mode.add_argument(f"--{key}", dest="mode", action="store_const",
                        const=key)
  mode.add_argument("--as", dest="child_key", default=None)
  # common
  p_new.add_argument("--archive", action="store_true")
  p_new.add_argument("--tag", action="append", default=[])
  p_new.add_argument("--template", default="")
  p_new.add_argument("--tmp",       action=BooleanOptionalAction, default=None)
  p_new.add_argument("--timestamp", action=BooleanOptionalAction, default=None)
  p_new.add_argument("--open",      action=BooleanOptionalAction, default=None)
  p_new.add_argument("--cd",        action=BooleanOptionalAction, default=None)
  p_new.add_argument("--ts-name",   action="store_true")
  p_new.add_argument("--alpha-name", action="store_true")
  p_new.add_argument("--prompt-name", action="store_true")
  p_new.add_argument("--post", action="append", default=[])
  p_new.add_argument("--yes", action="store_true")
  p_new.add_argument("--dry-run", action="store_true")
  p_new.add_argument("--multi", action="store_true")
  ```
  `b new --help` must list every option with a one-line description
  (argparse `help=...` on each). A separate `b help new` topic dumps
  the registered Sources + child Sources with their defaults.

- `n` alias: `sub.add_parser("n", parents=[p_new], add_help=False)`.
- **Remove** `migrate` from parser, dispatch, completion, and the
  error-suppression set in `cli/entry.py:323/330`.
- dispatch.py: replace both `new` and `migrate` branches with one call
  to `workspace.new.cmd_new(ns, base_dir, cwd)`.
- `cli/completion.py`:
  - drop `"migrate"` from `_TOP_LEVEL_COMMANDS`.
  - add `n`.
  - extend `_subcommand_candidates("new", ...)` to suggest mode flags,
    common flags, registered child-source keys after `--as`, and
    template names after `--template`.

---

## 11. Tests

`tests/test_new_*.py`:

- `tests/test_new_detect.py` — shape detection table: URL, SSH form,
  `.git`, github blob URL, `./x`, `x/`, `/abs`, `~/x`, bare token,
  no-input, mode-flag overrides.
- `tests/test_new_options.py` — three-layer resolution: Source defaults
  vs child defaults vs CLI; `--no-tmp` overriding a child's `tmp: true`.
- `tests/test_new_name.py` — name inference from URL/path/token,
  `--tmp`/`--timestamp`/`--ts-name`/`--alpha-name` combinations,
  conflict fails cleanly.
- `tests/test_new_empty.py` — marker + tags + log + cache upsert; refuses
  on existing target.
- `tests/test_new_local.py` — move into base; refuses src already under
  base; `--multi` runs N moves; `--multi` rejects a positional name.
- `tests/test_new_git.py` — uses a local bare repo as the URL so no
  network; clone lands at `<name>/repo`, marker at `<name>/`, log has
  the URL; failed clone rolls back.
- `tests/test_new_download.py` — uses a `http.server` on `localhost`
  in a fixture; verifies file lands inside the project dir, marker
  exists, log records the URL.
- `tests/test_new_downloaded.py` — fixture sets `downloads_dir` to a
  `tmp_path`; verifies most-recent file is picked, default
  tmp+timestamp applied.
- `tests/test_new_archive.py` — `--archive` works on empty, local, and
  git; archive timestamping matches today's `b migrate --archive` behavior
  (port the existing cases).
- `tests/test_new_adapters.py` — github/gitlab/bitbucket/codeberg URL
  → correct clone URL and correct raw rewrite.
- `tests/test_new_cli.py` — argparse round-trips for every documented
  invocation; mode flags are mutually exclusive; `--dry-run` writes
  nothing.

All tests use `tmp_path`. No fs/sqlite mocks (AGENTS.md §9).

---

## 12. Open questions

### 12.1 `b c` overlap
`b c <key>` is already templated quick-create. If `b new` gains
`--as <child-key>` reading the same config block, `b c` becomes a
shorthand for `b new --as`. Options:
- **(a) Leave `b c` alone**, but reuse the new options resolver
  underneath so they don't drift. Lowest risk.
- **(b) Make `b c` an alias for `b new --as`** and drop the parallel
  config key. Cleaner long-term, breaks anyone who scripted `b c`.

COMMENT: Lean (a). Confirm?
COMMENT: Remove "b c" entirely. I only want "b new".

### 12.2 `--multi`
Confirmed: `--multi` enables N positional inputs and disallows the
`<name>` positional (ambiguous which input gets the name). All inputs
share the same Source + options. Different Sources per item must be N
separate invocations.

COMMENT: Should `--multi` also work for git URLs / mixed inputs? Or
restrict to LocalDirSource since that's the migrate use case? Lean
"any Source, all-same".
COMMENT: Can be a mix. Add "--ask-source" as well to force it to ask the source for each item since this might not be guessing correctly.

### 12.3 URL detection without adapter
Decided: any URL with `.git` or SSH form is treated as git; everything
else is download. Adapters only add smart bare-URL detection +
blob→raw rewrites for known forges.

COMMENT: For a self-hosted GitLab URL like
`https://git.mycompany.com/team/proj`, with no adapter and no `.git`:
falls into DownloadSource and probably fails. User can always pass
`--git`. Lean: accept that and document it.
COMMENT: Rely on .git ending unless there is an adapter that rewrites the url

### 12.4 Archive extraction in DownloadSource
Auto-unpack `.tar.gz`/`.tar.xz`/`.zip`/`.7z`? Out of scope for v1 —
download lands the file; user runs `tar xf …`. Revisit after v1 ships.
COMMENT: Drop this functionality. Not planned

### 12.5 `b a` and `b fix`
You weren't sure these still earn their keep. Out of scope for this
TODO; leaving them alone. If you want them folded in too, file a
follow-up.

### 12.6 Source defaults config file location
`<base>/.config/new.yaml` proposed. Alternative: inline under the
existing global config (same file as `b c` templates). Lean: inline,
to keep config files few.

COMMENT: Confirm location, or say "inline under the existing prefs
file"?
COMMENT: Use global existing config. Don't invent a new config. There should be nothing about "b new" configured directly under a project. Only in ".homebase/config.yaml".

### 12.7 `--prompt-name` outside TUI
Today's `b c` uses `input()` for `prompt-name`. Keep that for CLI
`b new --prompt-name`. The full TUI modal is only reached by no-arg
`b new` (§7.6).
COMMENT: Rename it to --ask-name and incorporate it with the --ask-name comment mentioned earlier

### 13 (COMMENT)

* Every parameter and command implemented under "b new" should show up dyanamically in tab completions.
* --multi should be supported by all Sources!
* All sources should have a dedicated function to figure out the name if no name is provided, based on the context it has.
* There should be an option --ask-name (mutual exclusive to a name provided). --ask-name should also be possible in --multi. If given; b will print out some info about the item being processed and ask what it should be named. If options like --tmp is also provided, it should still add their logic to the given name
* The "new" interactive dialog box inside b should be expanded to support an interactive way of defining the parameters in "b new". I should be able to eg an url the same way. The options should also be reflected in the ui. This needs to be created in a dynamic way so that it doesnt need to be duplicated code/logic