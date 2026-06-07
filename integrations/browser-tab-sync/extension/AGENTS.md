# extension — Agent Instructions

Parent `../AGENTS.md` and repo-root rules apply.

MV3 extension built with [WXT](https://wxt.dev). TypeScript, strict.

## Layout

```
entrypoints/background.ts   Service worker: native-messaging port + dispatch
src/protocol.ts             Wire types (mirror of schema/native-messaging.schema.json)
src/native.ts               connectNative + send/receive helpers
src/reconcile.ts            Execute ensure/focus requests against the browser
src/tabs.ts                 chrome.tabs helpers
src/groups.ts               chrome.tabGroups helpers
src/observer.ts             Two-way sync: watch managed group, debounce, snapshot
```

## Rules

- The extension owns no file IO and no conflict policy — it queries/mutates the
  browser and streams snapshots. All decisions are made by the CLI/host.
- `src/protocol.ts` mirrors `schema/native-messaging.schema.json`. Keep both
  sides (and `cli/.../protocol.py`) in sync in one commit.
- Native host name is `nu.boa.homebase_bts` (see `wxt.config.ts`).
- Only act on the managed group; never touch other tabs/windows/groups.
- Debounce snapshots (~1000 ms); never send on every raw event.

## Commands

```
npm install
npm run dev          # Chrome + HMR
npm run compile      # typecheck
npm run build
```
