// Search box filtering, local and synchronous (no b process per keystroke).
// Like b's QUERY: `#tag` (exact, case-insensitive), `#ta*` (glob), `-#tag`
// excludes, other words must all appear in the name/subtitle/tags. The tag
// being typed (last word, no space after it yet) matches as a prefix so the
// list narrows while typing.

export type Searchable = {
  title: string;
  subtitle?: string;
  keywords: string[];
  tags: string[];
};

type TagTerm = { negate: boolean; test: (tag: string) => boolean };

export type ParsedQuery = {
  tagTerms: TagTerm[];
  words: string[];
  // The `#…` word being typed, for completion.
  typingTag?: { prefix: string; partial: string };
};

const TAG_RE = /^(-?)#(.*)$/;

function globRegex(pattern: string): RegExp {
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  return new RegExp(
    "^" + escaped.replace(/\*/g, ".*").replace(/\?/g, ".") + "$",
  );
}

export function parseQuery(text: string): ParsedQuery {
  const tokens = text.split(/\s+/).filter(Boolean);
  const typingLast = text.length > 0 && !/\s$/.test(text);
  const out: ParsedQuery = { tagTerms: [], words: [] };
  tokens.forEach((token, index) => {
    const m = TAG_RE.exec(token);
    if (!m) {
      out.words.push(token.toLowerCase());
      return;
    }
    const negate = m[1] === "-";
    const pattern = m[2].toLowerCase();
    const typing = typingLast && index === tokens.length - 1;
    if (typing) {
      out.typingTag = { prefix: `${m[1]}#`, partial: pattern };
    }
    if (!pattern) {
      return; // a lone "#" filters nothing yet
    }
    let test: (tag: string) => boolean;
    if (/[*?]/.test(pattern)) {
      const re = globRegex(pattern);
      test = (tag) => re.test(tag);
    } else if (typing && !negate) {
      test = (tag) => tag.startsWith(pattern);
    } else {
      test = (tag) => tag === pattern;
    }
    out.tagTerms.push({ negate, test });
  });
  return out;
}

function isSubsequence(needle: string, hay: string): boolean {
  let i = 0;
  for (const ch of hay) {
    if (ch === needle[i]) {
      i += 1;
      if (i === needle.length) {
        return true;
      }
    }
  }
  return needle.length === 0;
}

// Lower is better; undefined = no match.
function wordScore(word: string, item: Searchable): number | undefined {
  const title = item.title.toLowerCase();
  if (title.startsWith(word)) {
    return 0;
  }
  if (title.includes(word)) {
    return 1;
  }
  const rest = [item.subtitle ?? "", ...item.keywords, ...item.tags]
    .join(" ")
    .toLowerCase();
  if (rest.includes(word)) {
    return 2;
  }
  return isSubsequence(word, title) ? 3 : undefined;
}

export function filterItems<T extends Searchable>(
  items: T[],
  query: ParsedQuery,
): T[] {
  if (!query.tagTerms.length && !query.words.length) {
    return items;
  }
  const scored: { item: T; score: number; index: number }[] = [];
  items.forEach((item, index) => {
    const tags = item.tags.map((t) => t.toLowerCase());
    for (const term of query.tagTerms) {
      if (tags.some(term.test) === term.negate) {
        return;
      }
    }
    let score = 0;
    for (const word of query.words) {
      const s = wordScore(word, item);
      if (s === undefined) {
        return;
      }
      score += s;
    }
    scored.push({ item, score, index });
  });
  // Stable: equal scores keep the configured order (name / opened).
  scored.sort((a, b) => a.score - b.score || a.index - b.index);
  return scored.map((s) => s.item);
}

export type TagCount = { tag: string; count: number };

export function tagCounts(items: Searchable[]): TagCount[] {
  const counts = new Map<string, number>();
  for (const item of items) {
    for (const tag of new Set(item.tags.map((t) => t.toLowerCase()))) {
      counts.set(tag, (counts.get(tag) ?? 0) + 1);
    }
  }
  return [...counts.entries()]
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag));
}

// Completions for the `#…` word being typed: prefix matches first, then
// substring matches. None once it is exactly the only matching tag.
export function tagSuggestions(
  query: ParsedQuery,
  counts: TagCount[],
  limit = 8,
): TagCount[] {
  const typing = query.typingTag;
  if (!typing) {
    return [];
  }
  const partial = typing.partial;
  const prefix = counts.filter((c) => c.tag.startsWith(partial));
  const inner = counts.filter(
    (c) => !c.tag.startsWith(partial) && c.tag.includes(partial),
  );
  const out = [...prefix, ...inner].slice(0, limit);
  return out.length === 1 && out[0].tag === partial ? [] : out;
}

// The search text with the word being typed replaced by the completed tag.
export function completeTag(
  text: string,
  query: ParsedQuery,
  tag: string,
): string {
  const head = text.replace(/\S+$/, "");
  return `${head}${query.typingTag?.prefix ?? "#"}${tag} `;
}
