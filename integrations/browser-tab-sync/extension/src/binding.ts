// Remember which desired URL each managed tab was opened for, so redirects /
// added query params don't make us lose track of it and create duplicates.
//
// Session storage: stable within a browser session (tab ids are too). Cleared on
// browser restart, where we fall back to live-URL matching. The durable home for
// this is the host's state DB; this is the pragmatic in-extension version.

import { browser } from "wxt/browser";

const KEY = "bm:bindings";
const GROUP_KEY = "bm:groups";

type Stored = Record<string, Record<string, string>>; // profileId -> (tabId -> url)
type GroupStored = Record<string, number>; // profileId -> groupId

export type Binding = Record<number, string>;

export async function loadBinding(profileId: string): Promise<Binding> {
  const all = (await browser.storage.session.get(KEY))[KEY] as Stored | undefined;
  const stored = all?.[profileId] ?? {};
  const out: Binding = {};
  for (const [tabId, url] of Object.entries(stored)) out[Number(tabId)] = url;
  return out;
}

export async function saveBinding(profileId: string, binding: Binding): Promise<void> {
  const all = ((await browser.storage.session.get(KEY))[KEY] as Stored | undefined) ?? {};
  const stored: Record<string, string> = {};
  for (const [tabId, url] of Object.entries(binding)) stored[String(tabId)] = url;
  all[profileId] = stored;
  await browser.storage.session.set({ [KEY]: all });
}

export async function loadGroupBinding(profileId: string): Promise<number | undefined> {
  const all = (await browser.storage.session.get(GROUP_KEY))[GROUP_KEY] as GroupStored | undefined;
  return all?.[profileId];
}

export async function saveGroupBinding(profileId: string, groupId: number): Promise<void> {
  const all =
    ((await browser.storage.session.get(GROUP_KEY))[GROUP_KEY] as GroupStored | undefined) ?? {};
  all[profileId] = groupId;
  await browser.storage.session.set({ [GROUP_KEY]: all });
}
