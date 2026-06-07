// Minimal URL normalization for tab matching. Mirrors the intent of the CLI's
// urlnorm.py; only needs to be internally consistent for idempotency.

const STRIP = new Set([
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_term",
  "utm_content",
  "fbclid",
  "gclid",
  "mc_eid",
  "mc_cid",
  "igshid",
]);
const KEEP_FRAGMENT_HOSTS = new Set(["github.com"]);

export function normalize(raw: string): string {
  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    return raw;
  }
  u.protocol = u.protocol.toLowerCase();
  u.hostname = u.hostname.toLowerCase();
  for (const key of [...u.searchParams.keys()]) {
    if (STRIP.has(key)) u.searchParams.delete(key);
  }
  if (!KEEP_FRAGMENT_HOSTS.has(u.hostname)) u.hash = "";
  if (u.pathname.length > 1 && u.pathname.endsWith("/")) {
    u.pathname = u.pathname.replace(/\/+$/, "");
  }
  return u.toString();
}

export function sameUrl(a: string, b: string): boolean {
  return normalize(a) === normalize(b);
}
