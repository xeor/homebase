import { browser, type Browser } from "wxt/browser";
import { loadBinding, loadGroupBinding, saveGroupBinding } from "./binding";
import { ensureConnected, postToHost } from "./native";
import type { ProfileSnapshot, SnapshotTab } from "./protocol";

// Two-way sync observer. MV3 service workers are killed when idle and lose all
// in-memory state, so the set of watched profiles lives in storage.session and
// the group is resolved fresh on every change. Event listeners are registered at
// the top level (see background.ts) so a change wakes the worker and is handled.

const DEBOUNCE_MS = 1000;
const WATCHED_KEY = "bm:watched";

interface WatchInfo {
  title: string;
  groupId?: number;
}
type Watched = Record<string, WatchInfo>;

let timer: ReturnType<typeof setTimeout> | undefined;

async function getWatched(): Promise<Watched> {
  return ((await browser.storage.session.get(WATCHED_KEY))[WATCHED_KEY] as Watched | undefined) ?? {};
}

async function setWatched(watched: Watched): Promise<void> {
  await browser.storage.session.set({ [WATCHED_KEY]: watched });
}

export async function addWatch(profileId: string, title: string): Promise<void> {
  const watched = await getWatched();
  watched[profileId] = {
    title,
    groupId: watched[profileId]?.groupId ?? (await loadGroupBinding(profileId)),
  };
  await setWatched(watched);
  console.info("[homebase-bts] watching", profileId, title);
  scheduleSnapshot();
}

export async function removeWatch(profileId: string): Promise<void> {
  const watched = await getWatched();
  delete watched[profileId];
  await setWatched(watched);
}

export function scheduleSnapshot(): void {
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => void snapshotAll(), DEBOUNCE_MS);
}

async function snapshotAll(): Promise<void> {
  const watched = await getWatched();
  const entries = Object.entries(watched);
  if (entries.length === 0) return;
  ensureConnected();
  let mutated = false;
  for (const [profileId, info] of entries) {
    const snapshot = await readSnapshot(profileId, info.title);
    if (snapshot) postToHost(snapshot);
    const resolvedId = snapshot?.group_id;
    if (resolvedId !== undefined && resolvedId !== info.groupId) {
      watched[profileId] = { title: info.title, groupId: resolvedId };
      mutated = true;
    }
  }
  if (mutated) await setWatched(watched);
}

export async function readSnapshot(
  profileId: string,
  title: string,
  requestId?: string,
): Promise<ProfileSnapshot | undefined> {
  let group: Browser.tabGroups.TabGroup | undefined;
  const groupId = await loadGroupBinding(profileId);
  if (groupId !== undefined) {
    try {
      group = await browser.tabGroups.get(groupId);
    } catch {
      group = undefined;
    }
  }
  if (!group) {
    const matches = await browser.tabGroups.query({ title });
    if (matches.length > 1) {
      console.warn(
        "[homebase-bts] ambiguous watched group title; snapshot skipped:",
        title,
      );
      return undefined;
    }
    group = matches[0];
  }
  if (!group) return undefined;

  const tabs = await browser.tabs.query({ groupId: group.id });
  const binding = await loadBinding(profileId);
  const snapTabs: SnapshotTab[] = tabs
    .filter((t) => t.id != null)
    .sort((a, b) => a.index - b.index)
    .map((t) => ({
      browser_tab_id: t.id as number,
      url: t.url ?? t.pendingUrl ?? "",
      managed_url: binding[t.id as number],
      title: t.title,
      active: t.active,
      index: t.index,
    }));

  const snapshot: ProfileSnapshot = {
    type: "profile_snapshot",
    ...(requestId !== undefined ? { request_id: requestId } : {}),
    profile_id: profileId,
    browser: "chrome",
    group_id: group.id,
    group: { title: group.title, color: group.color, collapsed: group.collapsed },
    tabs: snapTabs,
  };
  await saveGroupBinding(profileId, group.id);
  return snapshot;
}
