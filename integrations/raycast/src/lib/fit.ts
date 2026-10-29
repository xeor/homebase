// Fit a list row into Raycast's fixed row width. Raycast never truncates a
// row itself: a too long subtitle or too many accessories push the rightmost
// accessory (the herdr pane count) under the ⌘1-9 column. Widths below were
// measured in the default 750 pt window (accessibility frames).

// Usable row width: title start to the ⌘1-9 column, minus a safety margin.
export const ROW_BUDGET_PX = 660;
const TITLE_PX = 7.0; // per character, a little above measured (6.3-6.7)
const SUBTITLE_PX = 6.8; // measured 6.5
const PILL_PX = 7.4; // pill text, measured 7.1
const PILL_PAD_PX = 35; // padding + gap per pill
const TITLE_GAP_PX = 12; // title to subtitle
const SUBTITLE_GAP_PX = 20; // subtitle to the first accessory
const MIN_TITLE_CHARS = 12;
const MIN_SUBTITLE_CHARS = 10;

export type Marker =
  | { kind: "pill"; text: string }
  | { kind: "count"; text: string };

export type FitInput = {
  title: string;
  subtitle: string;
  tags: string[];
  markers: Marker[]; // herdr markers, always shown
};

export type FitResult = {
  title: string;
  subtitle: string;
  tags: string[]; // shown as pills, "#" added by the caller
  hiddenTags: string[]; // shown as one "+N" pill
};

const AGO_UNITS: Record<string, string> = {
  minute: "m",
  hour: "h",
  day: "d",
  week: "w",
  month: "mo",
  year: "y",
};

// "27 minutes ago" -> "27m", "just now" -> "now".
export function compactAgo(text: string): string {
  return text
    .replace(
      /\b(\d+) (minute|hour|day|week|month|year)s? ago\b/g,
      (_m, n: string, unit: string) => `${n}${AGO_UNITS[unit]}`,
    )
    .replace(/\bjust now\b/g, "now");
}

export function cut(text: string, chars: number): string {
  if (text.length <= chars) {
    return text;
  }
  return chars <= 2 ? "" : text.slice(0, chars - 2).trimEnd() + "..";
}

function pillPx(text: string): number {
  return text.length * PILL_PX + PILL_PAD_PX;
}

function markerPx(marker: Marker): number {
  // count = terminal icon + number, measured ~45 px before the number.
  return marker.kind === "count"
    ? 45 + marker.text.length * PILL_PX
    : pillPx(marker.text);
}

function subtitlePx(subtitle: string): number {
  return subtitle ? TITLE_GAP_PX + subtitle.length * SUBTITLE_PX : 0;
}

function tagsPx(tags: string[], hidden: number): number {
  const shown = tags.reduce((sum, tag) => sum + pillPx(`#${tag}`), 0);
  return shown + (hidden ? pillPx(`+${hidden}`) : 0);
}

export function fitRow(input: FitInput): FitResult {
  let title = input.title;
  const fixed =
    SUBTITLE_GAP_PX + input.markers.reduce((sum, m) => sum + markerPx(m), 0);
  let subtitle = compactAgo(input.subtitle);
  let tags = [...input.tags];
  const hiddenTags: string[] = [];
  const width = () =>
    fixed +
    title.length * TITLE_PX +
    subtitlePx(subtitle) +
    tagsPx(tags, hiddenTags.length);
  const fits = () => width() <= ROW_BUDGET_PX;

  // 1. Fewer tag pills, keeping the first one ("#a +2").
  while (!fits() && tags.length > 1) {
    hiddenTags.unshift(tags.pop() as string);
  }
  // 2. Cut the subtitle with "..", down to a short stub.
  while (!fits() && subtitle.length > MIN_SUBTITLE_CHARS) {
    subtitle = cut(subtitle, subtitle.length - 1);
  }
  // 3. Only "+N" for the tags.
  if (!fits() && tags.length) {
    hiddenTags.unshift(...tags);
    tags = [];
  }
  // 4. Whatever subtitle still fits.
  while (!fits() && subtitle) {
    subtitle = cut(subtitle, subtitle.length - 1);
  }
  // 5. Last resort: the name itself.
  while (!fits() && title.length > MIN_TITLE_CHARS) {
    title = cut(title, title.length - 1);
  }
  return { title, subtitle, tags, hiddenTags };
}
