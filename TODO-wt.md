# TODO-wt — Worktree Support in `b`

Status: design draft, not implemented. Iterate inline.

## 1. Goal

Make long-lived (and short-lived) git worktrees first-class projects
in homebase so they show up in the TUI with their own tags, WIP flag,
opened-time, description, notes, etc. Branch-as-worktree should feel
as native as cloning a new project.

Concrete shape: one repo with three checked-out branches becomes three
rows in `b`: `foo`, `foo-featx`, `foo-bugfixy`. Each row is
independent for tagging/filtering but knows its parent.

## 2. Worktrunk

Looked at worktrunk.dev as a possible backend. Decision: not used.
Native implementation, no compat layer, no escape-hatch shell-out, no
hooks framework borrowed. The research is parked.

## 3. Data model

### 3.1 Layout & naming

Worktrees are sibling project directories under `<base>/`. Separator
is `-` (not `.`).

```
<base>/
├── foo/                 # main project (regular clone)
│   ├── repo/            # working tree, branch = main
│   └── .base.yml
├── foo-featx/           # worktree project
│   ├── repo/            # git worktree, branch = featx
│   └── .base.yml        # has a worktree: block (see §3.2)
└── foo-bugfixy/
    ├── repo/
    └── .base.yml
```

CLAUDE-COMMENT: Branch names can contain `/` (e.g. `feature/auth`),
which can't go into a directory name. Pick one:
(a) replace `/` with `--` → `foo-feature--auth`
(b) replace `/` with `__` → `foo-feature__auth`
(c) keep only the leaf segment → `foo-auth` (loses namespace)
(d) reject branches with `/` in `b new`, force the user to rename
Default proposal: (a). The raw branch name still lives in
`.base.yml`, so this only affects the directory name.
COMMENT: Lets use a, name them --

CLAUDE-COMMENT: If `<parent>-<branch>` already exists as a directory
under `<base>/` (worktree or regular project), what should `b new`
do? Error out, auto-suffix (`-2`, `-3`), or prompt? Default
proposal: error out, force the user to pick a different branch name
or remove the conflict.
COMMENT: Correct, hard error

### 3.2 `.base.yml` schema

Add a single new top-level key, `worktree`, as a dict. Presence of
this key means the project is a worktree. No separate `kind` field.

```yaml
# only present on worktree projects:
worktree:
  of: foo                 # parent project name (directory under <base>/)
  branch: feature/auth    # raw git branch, unescaped
  upstream: origin/main   # optional, merge target hint
  created_from: abc1234   # sha of parent HEAD when worktree was made
```

Regular projects: no change, no `worktree:` key.

Add `worktree` to `BASE_META_ALLOWED_KEYS` and to the schema
validator (`metadata/utils.py`). Validator must check that `of` is a
non-empty string, `branch` is a non-empty string, the others are
optional.

CLAUDE-COMMENT: Do we want to record `upstream` and `created_from` at
creation time even though there's no merge command yet, or skip them
until a real consumer exists? Default proposal: skip both for now —
only `of` and `branch`. Add the rest when a feature actually reads
them.
COMMENT: Drop them. Not sure if we need upstream or created_from

CLAUDE-COMMENT: When creating a worktree, what (if anything) should
be copied from the parent's `.base.yml` to the new worktree's
`.base.yml`? Options: nothing (clean slate), description only, tags
only, description+tags. Default proposal: nothing. WIP is already
explicit per your earlier note.
COMMENT: Nothing should be copied

### 3.3 Git detection (`.git` file vs dir)

Two concrete code changes:

1. `workspace/projects.py:git_info()` currently does
   `(.git).is_dir()` and returns `("-", "-", 0)` otherwise. That
   skips every worktree. Change to `.exists()` and let `git -C`
   handle both cases.
2. The GIT column rendering must visibly distinguish worktree from
   regular repo. The information lives in `repo/.git`: directory =
   regular, file with `gitdir: …` = worktree.

The built-in `GIT` property (`dir-exists: [.git]`) stays as-is. We
add an example to `docs/kitchen-sink-config.md` showing how a user
can configure a property that matches either form, or only one.

CLAUDE-COMMENT: For the GIT column, pick a compact format that fits
in ~20 chars next to the branch name. Three concrete options:
(a) `featx*  ↪foo`     — branch first, arrow + parent name suffix
(b) `[wt] featx*`      — `[wt]` prefix tag, parent not shown
(c) `foo:featx*`       — parent:branch, colon-separated
Regular repos still render as `main*` / `featx*` only. Default
proposal: (a), because the parent name is the high-value extra info.
COMMENT: Let's try a first.

## 4. Filter syntax

Introduce a dynamic structured-filter syntax in the query bar,
separate from `#tag` and free-text. Form: `:<key>=<value>`.

First filter, used by worktrees:

- `:git-worktree-of=foo` — matches all worktrees whose parent is `foo`

This must be a generic mechanism, not a worktree-only special case.
Future filters will land under the same `:<key>=<value>` shape
(`:git-branch=main`, `:size>10M`, etc. — exact set is out of scope
here). Implementation expectations:

COMMENT: Lets also move over existing dynamic elements like "last=..." as well. No need to keep backward compatibility. But make sure docs and such is also updated

- Tokeniser recognises a leading `:` on a query token and parses
  `key=value` (or other operators we add later).
- Query bar gets syntax highlighting for `:key=value` tokens (key
  one colour, operator another, value a third), same way `#tag` and
  free-text are already coloured differently.
- Unknown keys still parse but match nothing, with a non-fatal hint
  in the input area (don't block the filter — homebase rule: no
  migration blocks, [[feedback_no_migration_blocks]]).
- Filter engine in `filter/engine.py` gains a registry of `key →
  matcher(row) -> bool` so adding more later is one entry.

CLAUDE-COMMENT: Operator. You wrote `:git-worktree-of=foo`. Confirm
`=` is the only operator for now (equality), and we reserve `!=`,
`>`, `<`, `~` (regex/glob) for later. Default proposal: `=` only in
v1, parser accepts the others but the engine warns "operator not
implemented" until we wire each one up.
COMMENT: Correct, but querylang needs to support them even tho we don't need to implement it yet

CLAUDE-COMMENT: Should `:git-worktree-of=foo` also match `foo`
itself (i.e. the parent row), so the filter shows "this repo and
its worktrees"? Or strictly worktrees? Default proposal: strictly
worktrees. Use `:git-worktree-of=foo OR name=foo` if you want both.
COMMENT: I want both, but in that case the name must change to something that covers both. Come up with some examples.

## 5. Creating worktrees — via `b new`

No dedicated `b wt new` subcommand. Worktree creation is a new
source kind in the existing `b new` plumbing.

### 5.1 CLI

```sh
# from anywhere — pick parent explicitly:
b new <branch> --as worktree --from <parent-project>

# from inside an existing project — `.` means "the project I'm in":
# COMMENT: yes, but I want the syntax shorter. I want "b new <name>" to auto on worktree with that name. Auto must default to worktree if inside project folder, and git exists. This must also work if I want a new worktree out of an existing one.
b new <branch> --as worktree --from .

# shorter form when current directory is a project (auto-detects --from):
b new . <branch> --as worktree
```

Semantics:

- `--from <project>` resolves to a sibling under `<base>/`.
- `--from .` walks up from `cwd` to find the enclosing project
  (looks for `.base.yml`, same logic as `b cd .`).
- Branch handling:
  - If the branch already exists locally, `git worktree add` checks
    it out into the new path.
  - If the branch doesn't exist, it's created from a base ref —
    see open question below.
- Output path: `<base>/<parent-name><sep><sanitised-branch>/repo/`
  where `<sep>` is `-`.
- A `.base.yml` is written next to `repo/` with the `worktree:`
  block from §3.2.
- Single-selection only — never operates on a multi-select.

### 5.2 TUI

`ctrl-n` opens the existing new-project dialog. When a worktree
candidate is selected (single-select), the dialog is pre-filled:

COMMENT: no, ctrl-n shoulnt autofill. There should be a new action that is named something like "New worktree" available in the normal action list. That new action should open the same dialog box as ctrl-n, but prefilled.

- "source" set to `worktree`
- "parent" set to the selected row's project name
- "name" field empty, awaiting the branch name (treated as the
  worktree branch, not the directory name — directory is computed)

If the dialog is opened with no selection or a multi-selection, the
`worktree` source is not pre-selected; user can still pick it
manually from the source dropdown.

CLAUDE-COMMENT: Base ref for new branches. When `b new <branch>
--as worktree` is called and `<branch>` doesn't exist yet, what ref
does the new branch start from? Options:
(a) parent repo's current HEAD
(b) parent repo's default branch (main/master, detected)
(c) explicit `--base <ref>` required, no default
Default proposal: (a) — parent's HEAD — because that matches what
`git worktree add -b new` does by default and is the least
surprising.
COMMENT: yes, if that is the default thats what we are doing. If other functionality is acting against the default behavior, we should also reconsidder. Please add comments if that is the case.

CLAUDE-COMMENT: From the TUI, after the worktree is created, do we
land in the new worktree directory (existing `b new --open`
behaviour) or stay in the current project? Default proposal: same
as `b new` default — follow whatever the global `open` / `cd`
default is for `b new`, no special case.
COMMENT: follow global

## 6. Removing worktrees — via existing delete

No dedicated `b wt rm`. The existing delete action must learn to do
the right thing for a worktree-kind row:

- Run `git worktree remove <path>` (or `git worktree remove --force`
  if the user confirms a dirty-tree force) before / instead of just
  `rm -rf`ing the directory.
- Clean up the parent repo's `.git/worktrees/<name>/` admin entry.
- Leave the branch alone by default. Branch deletion is a separate
  manual step the user can do in git directly, until we have
  evidence it's needed inside `b`.

CLAUDE-COMMENT: When deleting the *parent* project of one or more
worktrees, what's the policy?
(a) Refuse — user must delete worktrees first.
(b) Cascade — delete all worktrees automatically (with confirm).
(c) Orphan — delete parent, leave worktree directories as "broken"
   rows that surface in the TUI for manual cleanup.
Default proposal: (a) refuse with a clear message listing the
worktrees that block the delete.
COMMENT: Show warning with info and list. If still accepted it should delete parent and leave them broken.

## 7. Reference integrity on moves and archive

This is the hard part and the most important one. A git worktree is
held together by two pointers that both contain absolute paths:

- `<worktree>/repo/.git` is a file with `gitdir:
  <absolute-path-to-parent>/.git/worktrees/<id>`.
- `<parent>/.git/worktrees/<id>/gitdir` is a file with
  `<absolute-path-to-worktree>/repo/.git`.

Any time `b` moves a directory, those pointers must be rewritten or
the worktree silently breaks (`fatal: not a git repository`).

Concrete obligations:

1. **Renaming a worktree project** (`b mv foo-featx foo-newname`):
   rewrite `<parent>/.git/worktrees/<id>/gitdir` to the new path.
2. **Archiving a worktree project** (`b archive mv foo-featx`):
   same as rename, but new path is under `_archive/…`. The
   archived worktree must still be a working git repo when the
   user `cd`s into it.
3. **Renaming the parent project** (`b mv foo bar`): walk every
   worktree row with `worktree.of == foo`, rewrite each one's
   `repo/.git` file to the new parent path, and update the
   `worktree.of` in their `.base.yml`.
4. **Archiving the parent project**: same as rename, but to an
   archive path. Open question below.
5. **Packed-archive worktrees**: the existing tar-pack flow must
   either refuse to pack a worktree (because the gitdir pointer
   would freeze a path that no longer resolves on restore) or pack
   it and rewrite pointers on unpack. See open question.

COMMENT: Make sure this works on all ways archive can be triggered, both in tui and cli. Same with renaming and such. There must also be a "b fix" handler for fixing broken repositories. b fix must see inside the .base.yaml to find worktree's and verify them. If there is something wrong it must suggest a fix. b fix must also handle moved base folders (if the path's in git needs to be absolute). In case of moved base folder, it must calculate and find where the new worktree folders are located

CLAUDE-COMMENT: Archiving the parent — what's the desired
behaviour?
(a) Move parent + all its worktrees together, rewriting pointers,
   so the whole family lives under `_archive/<year>/…`.
(b) Refuse to archive the parent while any of its worktrees are
   still active (non-archived).
(c) Allow archiving parent without touching worktrees, and rewrite
   pointers so worktrees keep working against the archived parent.
Default proposal: (a). Worktrees of an archived repo conceptually
belong with that repo, and (c) means worktrees keep depending on an
archived parent — fragile.
COMMENT: refuse to move if parent while there are still worktrees. However, there should be an action that can run on worktrees that moves the worktree into a fully cloned version of the same repo instread. Essentially "de worktreeing" it making it standalone. This new action should be suggested if trying to remove the parent, ie, suggest running this action to make the worktrees standalone before moving. There should also be an option to move everything together without making them standalone, ie, option a.

CLAUDE-COMMENT: Packed archives (`.tar.zst` or similar) of
worktrees. Options:
(a) Refuse — packing a worktree is not supported; user must
   un-worktree it (`git worktree remove`) before packing.
(b) Pack as a normal directory; on restore, the gitdir pointer is
   probably stale and we rewrite or warn.
(c) Pack the worktree *and* its admin entry in the parent, so
   restore reconstructs both. Most work, most robust.
Default proposal: (a) refuse. The worktree concept depends on a
live parent; freezing one side in a tarball asks for trouble.
COMMENT: Let it be stale, but make sure enough info is kept in .base.yaml so we would be able to repair later. Give warning when packing. And detect this when unpacking to see if we can repair it.

## 8. Risks and side-effects

- **Cache invalidation.** `git_info()` caches by `(refs_sig,
  head_sig)`. All worktrees of one repo share `.git/refs`, so any
  commit anywhere invalidates the row for every sibling worktree.
  Acceptable for v1; revisit if it becomes a hot path.
- **Tag symlinks.** A worktree and its parent can share tags. The
  symlink namer (`_safe_link_name`) already disambiguates by full
  project name, so `_tags/work/foo` and `_tags/work/foo-featx`
  coexist. Verify with a test.
- **Discovery prune.** Make sure the walker doesn't treat the
  worktree's `.git` *file* as a marker that needs special handling
  (it currently keys on `.base.yml`, so this should be fine, but
  audit).
- **Stale worktree rows.** A worktree directory can exist on disk
  while `git worktree list` no longer knows about it (e.g. the
  user ran `git worktree prune` manually). The row should still
  render — it's a "broken worktree" state — and surface a health
  warning in the info pane.

## 9. Implementation order

Each step ships independently and leaves the tool usable.

1. **Fix `.git` detection.** `git_info()` and any siblings that
   special-case `.git` as a directory. Tests with a real worktree
   under `tmp_path`.
2. **Schema.** Add `worktree` to `BASE_META_ALLOWED_KEYS` and the
   schema validator. Tests for the validator.
3. **GIT column rendering.** Pick the format from the §3.3 open
   question, render parent-name suffix for worktree rows.
4. **Dynamic `:key=value` filter framework.** Generic parser,
   registry, syntax highlight. First registered key:
   `git-worktree-of`. Tests for parser + matcher.
5. **`b new --as worktree`** (CLI), including `--from .` walk-up.
   Tests with real git.
6. **ctrl-n pre-fill** in TUI when a single worktree-eligible row
   is selected.
7. **Delete-action wiring** for worktree rows (`git worktree
   remove` + admin cleanup).
8. **Rename / archive pointer rewriting.** §7 items 1–3 first.
   Then §7 item 4 once the open question is settled.

Items 9+ (merge, sync, prune, packed-archive policy) are parked
until we see real friction.
