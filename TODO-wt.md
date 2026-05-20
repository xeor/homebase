# TODO-wt — Worktree Support in `b`

Status: design draft, not implemented. Iterate on this file.

## 1. Goal

Make long-lived (and short-lived) git worktrees first-class projects in
homebase so they show up in the TUI with their own tags, WIP flag,
opened-time, description, notes, etc. Add a small set of commands and
TUI affordances to make branch-as-worktree the dominant flow.

Concrete shape: one repo with three checked-out branches becomes three
rows in `b`: `foo`, `foo.feat-x`, `foo.bugfix-y`. Each row is
independent for tagging/filtering but knows its parent.

## 2. Worktrunk: integrate, replace, or skip?

**TL;DR — skip the dependency, steal the conventions.**

What worktrunk gives us:

- Path template `../<repo>.<branch>` for worktree placement.
- `wt switch / list / merge / remove` UX.
- Post-create hooks (install deps, start dev server, port hashing).
- LLM commit message generation.
- Per-repo state under `.git/wt/` (logs, CI cache).

Why not adopt it as a backend:

- **No machine-readable API.** It's CLI-first; `wt list` is text and
  there's no documented JSON output. Parsing stdout is fragile.
- **Approvals.toml UX** — every project hook needs first-run approval.
  That fights the homebase "no migration blocks" rule
  ([[feedback_no_migration_blocks]]).
- **Two config worlds.** `~/.config/worktrunk/config.toml` + per-repo
  `.config/wt.toml` would sit alongside `.homebase/config.yaml` and
  `.base.yml`. Three sources of truth.
- **Wrong philosophy.** Worktrunk optimises for many ephemeral AI-agent
  worktrees you trash. We want long-lived branches as durable
  projects. The semantics overlap but the defaults differ.
- **Extra runtime dep.** Rust binary install per machine; version
  drift; not available on all our targets.

What we should keep from worktrunk:

- Path layout: `<base>/<repo>.<branch>/repo/` mirrors their
  `../<repo>.<branch>` exactly. Makes interop trivial if the user ever
  runs `wt` against a homebase project.
COMMENT: Lets keep it simple and use <projectname>-<worktree>/repo instead. So, a "-", not "."

- Hook event names (`post-create`, `pre-merge`, `post-merge`) for
  consistency.
COMMENT: We don't need this functionality

- Optional escape-hatch flag: `b wt merge --via wt` shells out to
  worktrunk if installed, for users who want its merge ergonomics. No
  default delegation.
COmMENT: no need

**Verdict:** native implementation, with worktrunk-compatible layout so
you can layer worktrunk on top later without a migration.
COMMENT: I don't use worktrunk, so there is no need to keep a compatibiltiy or support anything from it. I was just looking into alternatives.

## 3. Data model

### 3.1 Where worktrees live

Convention: worktree is a sibling project directory.
COMMENT: Needs to be updated from comments above.

```
<base>/
├── foo/                 # main project (clone)
│   ├── repo/            # working tree, branch = main
│   └── .base.yml        # tags, wip, etc.
├── foo.feat-x/          # worktree project
│   ├── repo/            # git worktree, branch = feat-x
│   └── .base.yml        # kind: worktree, worktree_of: foo, branch: feat-x
└── foo.bugfix-y/
    ├── repo/
    └── .base.yml
```

- The worktree's `repo/.git` is a *file* (gitdir pointer), not a dir.
- Naming: `<parent-name>.<sanitised-branch>`. Slashes in branch →
  `__` (e.g. `feature/auth` → `foo.feature__auth`). Keep raw branch
  name in `.base.yml`.
- Reusing the existing suffix mechanism: worktrees get
  `suffix: wt` alongside today's `tmp` and `fork`
  (`core/constants.py:374`).
COMMENT: Suffixes is untouched because of comments above

### 3.2 `.base.yml` schema additions

Add to `BASE_META_ALLOWED_KEYS` in `core/constants.py:469`:

```yaml
# new keys for worktree projects:

# Lets assume it's a worktree if worktree_of is set, this is not needed
kind: worktree            # one of: project (default, implicit), worktree

# Lets add worktree as a dict instead with worktree.of, worktree.branch and so on.
worktree_of: foo          # parent project name (sibling under <base>/)
branch: feature/auth      # raw git branch, unescaped
upstream: origin/main     # merge target (optional, default config)
created_from: abc1234     # sha when worktree was created
ttl_days: 7               # optional auto-archive when merged+stale
```

For non-worktree projects no change.

### 3.3 Discovery & detection

Two real bugs to fix before anything else:

1. **`workspace/projects.py` `git_info()` checks `(.git).is_dir()`.**
   That returns False for a worktree. Either swap to `.exists()` and
   let `git -C` figure it out, or explicitly handle the gitdir-file
   case.
COMMENT: This must be updated. I want it to look different in the columns as well if it is a worktree or not.

2. **Built-in `GIT` property uses `dir-exists: [.git]`.** Same problem;
   needs `path-exists` or a dedicated detector.
COMMENT: No need to change anything here except updating kitchen-sink-config with examples how to add it so it can detect both types or both together.

Then add a new built-in property `WT` (label "worktree", detector =
`.git` is a regular file containing `gitdir:`). Once that's in,
filters like `#wt` and `kind:worktree` Just Work.

## 4. TUI changes

Smallest useful set:

- **New column** (optional, off by default): `wt_of` — shows parent
  project name for worktree rows.
COMMENT: No need to add another column. Info about worktree should be visible in a compact form in the git column

- **Filter sugar** in the query bar:
  - `kind:wt` / `kind:worktree`
  - `wt-of:foo` — all worktrees of `foo`
  - `branch:feat-*` — glob match on branch name
COMMENT: ":git-worktree-of=...", must support syntax highlight. We will add multiple other filters later with : prefix, so this must be dynamic.

- **Grouping mode** (table view setting):
  - `expand` — flat list, all worktrees as siblings (default)
  - `group` — parent project + worktrees folded under it; expand with
    a key. Implemented as a view-level sort/indent, not a tree widget,
    to avoid rewriting the table.
COMMENT: No need to group them

- **Hotbar actions** (target scope, dispatch via existing actions
  mechanism):
  - `wt_new` — prompt branch name, create worktree from selected row's
    repo
  - `wt_switch` — alias for "open this worktree" (= existing open
    action, mention here for discoverability)
  - `wt_merge` — confirm prompt → merge into upstream
  - `wt_rm` — confirm prompt → remove worktree + delete branch
COMMENT: They are not specific hotbar actions, but generic actions. I want one to create a new worktree from the one selected. It must be for only the selected (not multiple select), I want it to fill in the new dialog (ctrl-n), with the name of the project, and source set to "worktree". This is a new functionality in the "new" handler. It should also be possible from the CLI
COmMENT: remove needs to be handled by delete action

- **Status badges** in info pane:
  - `behind: 3, ahead: 1` vs upstream
  - `merged: yes/no` (is this branch already merged into upstream?)
  - `worktree health: ok / detached / branch-gone / conflicted`

## 5. Commands

All under `b wt <subcommand>`. Live in `commands/worktree.py`.

```sh
b wt new <branch> [--from <project>] [--track <ref>] [--open]
                    [--ttl <days>] [--tag <t>...]
    # creates <base>/<from>.<branch>/repo, runs git worktree add,
    # writes .base.yml with kind=worktree, optional copy of NOTES.md
    # template from parent.
# COMMENT: should be handled by "b new" and the same syntax as that is using. I must also be able to do this inside an existing project with "b new . ..." as example

b wt ls [<project>]
    # list worktrees (for one repo, or all). same output style as
    # `b ls`. accepts query: `b wt ls #wip`.
# COMMENT: Should be seen in "b ls", and it's filter functionality

b wt rm <project> [--delete-branch] [--force]
    # remove the worktree dir + git worktree remove + optionally
    # delete the branch. archives notes if any.
# COMMENT: Should be handled by normal delete

b wt merge <project> [--into <ref>] [--strategy squash|merge|rebase]
                       [--push] [--rm-after] [--via wt]
    # merge the worktree's branch into <ref> (default upstream from
    # .base.yml or config). --via wt delegates to worktrunk if
    # installed.
# COMMENT: Lets wait and see what's needed

b wt switch <project>
    # alias for `b cd <project>` for muscle-memory parity with wt.
# COMMENT: Lets wait and see what's needed

b wt sync [<project>]
    # fetch + show ahead/behind for all worktrees of a repo, refresh
    # cache row.
# COMMENT: Lets wait and see what's needed

b wt prune
    # find worktree dirs whose branch is merged/gone and offer to
    # archive or remove (interactive).
# COMMENT: Lets wait and see what's needed
```

Behaviour rules:

- **No git side-effects without confirmation by default.** `--yes`
  flag to skip prompts. Aligns with [[feedback_no_git_actions]].
- `b wt rm` never force-deletes an unmerged branch unless `--force`.
- `b wt merge --push` is opt-in, never default.

## 6. Lifecycle walkthroughs

### 6.1 Short-lived experiment

```sh
b wt new spike-xyz --from foo --tag scratch --ttl 3
# work in <base>/foo.spike-xyz/repo/
b wt merge foo.spike-xyz --strategy squash --rm-after
```

COMMENT: No, I don't want magic deletion

### 6.2 Long-lived feature branch

```sh
b wt new feature/auth --from foo --tag work --tag auth
# tagged independently, shows in TUI as its own row, can be WIP
# toggled separately, has its own NOTES.md.
# weeks later:
b wt sync foo.feature__auth
b wt merge foo.feature__auth --strategy merge --push
```

COMMENT: Lets wait and see whats needed

### 6.3 Permanent parallel branch (release/stable)

```sh
b wt new release/2.x --from foo --track origin/release/2.x
b tag add stable foo.release__2.x
# never merged back, stays around indefinitely.
b wt prune  # leaves it alone — branch isn't gone or merged.
```

COMMENT: Lets wait and see

## 7. Risks & open questions

**Hard problems:**

- `.git` as file vs dir runs through more code than just
  `git_info()`. Need a sweep:
  `grep -rn "\.git" src/homebase/` and audit each. Some property
  detectors and discovery prune logic may treat `.git` specially.
- Archive flow: `b archive mv foo.feat-x` should run
  `git worktree remove` first, otherwise the parent repo keeps a
  dangling worktree entry. Needs a hook into `archive/ops.py`.
  - COMMENT: I want references to be updated when things are moved around using b. I should be able to go into an archived worktree and still use git. Even if worktree moves, or if the main repo moves.

- Tag symlinks (`_tags/<tag>/<proj>`): if a worktree and its parent
  share a tag, both appear under that tag dir. Fine, but symlink
  names must not collide — already disambiguated by
  `_safe_link_name` so probably ok; verify.
- Cache invalidation: `git_info()` caches by `(refs_sig, head_sig)`.
  Worktrees write to shared `.git/`, so a commit in one worktree
  changes the signature for all of them. Either cache per-worktree
  HEAD only, or accept extra cache misses.
- `b new --git <url>` should optionally create the main project +
  pre-allocate a default branch worktree layout. Probably out of
  scope for v1.

**Open questions (user, please answer inline):**

1. Naming: `foo.feat-x` (worktrunk-compat) vs `foo/wt/feat-x` (nested,
   visually grouped, but harder to discover and `b cd` UX is worse).
   Default proposal: flat `foo.feat-x`.
   → answer: COMMENT: flat, see previous comments

2. Parent linkage: store `worktree_of: foo` in `.base.yml` *and*
   derive it from the directory prefix, or rely on prefix only?
   Storing it is more robust (rename-safe); derivation is simpler.
   Default proposal: store explicitly, derive as fallback.
   → answer: already commented

3. Should `b wt new` always set `wip: true` on the new row? Helps with
   "show me what I'm actively branched on" filters.
   → answer: no, I must set wip explicit

4. Worktrunk escape hatch: keep `--via wt` for `merge` only, or also
   for `new` and `rm`? More surface = more support burden.
   Default proposal: `merge` only, since that's where worktrunk adds
   real value (squash + cleanup + LLM commit msg).
   → answer: no merge functionality yet

5. TTL: when `ttl_days` elapses *and* the branch is merged, do we
   auto-archive, auto-remove, or just flag? Auto-anything is scary;
   I'd start with "flag with a property `wt_stale` and let the user
   run `b wt prune`".
   → answer: no auto

6. Should `b wt ls` be its own command or just sugar for
   `b ls kind:wt`? Less surface = better, unless we want richer
   per-repo output (ahead/behind columns).
   → answer: already commented

## 8. Implementation order (if we proceed)

1. Fix `.git` detection bugs across the codebase (small PR, valuable
   on its own — worktree users today already hit this).
2. Add `kind`, `worktree_of`, `branch`, `upstream`, `ttl_days` to
   `BASE_META_ALLOWED_KEYS`. Tests.
3. Add `wt` suffix + `WT` property. Tests.
4. `b wt new` + `b wt ls`. Tests with `tmp_path` and a real git repo.
5. `b wt rm` + archive hook integration.
6. `b wt merge` (native, no `--via wt` yet) + `b wt sync` +
   `b wt prune`.
7. Filter sugar (`kind:`, `wt-of:`, `branch:`) in query bar.
8. TUI grouping mode + status badges.
9. Optional `--via wt` delegation for `merge`.

Each step should leave the tool fully usable; no half-landed kinds.
