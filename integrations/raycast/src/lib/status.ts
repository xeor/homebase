// Small colored icons instead of text pills. Agent states: blocked red,
// working yellow, done green. Blue is general status (current space, panes).
import { Color, Icon, List } from "@raycast/api";
import { FitResult, Marker } from "./fit";

const AGENT_COLORS: Record<string, Color> = {
  working: Color.Yellow,
  blocked: Color.Red,
  done: Color.Green,
  idle: Color.SecondaryText,
};

// Most urgent first.
const AGENT_ORDER = ["blocked", "working", "done", "idle", "unknown"];

export type AgentInfo = { name: string; status: string };

export function agentRank(status: string): number {
  const rank = AGENT_ORDER.indexOf(status);
  return rank < 0 ? AGENT_ORDER.length : rank;
}

export function agentColor(status: string): Color {
  return AGENT_COLORS[status] ?? Color.SecondaryText;
}

function worstStatus(agents: AgentInfo[]): string {
  const states = agents.map((a) => a.status);
  return AGENT_ORDER.find((s) => states.includes(s)) ?? "unknown";
}

export function agentIcon(status: string) {
  return { source: Icon.Stars, tintColor: agentColor(status) };
}

// Fit markers matching statusAccessories (icon + optional number each).
export function statusMarkers(
  agents: AgentInfo[],
  paneCount: number | undefined,
  current = false,
): Marker[] {
  const out: Marker[] = [];
  if (current) {
    out.push({ kind: "count", text: "" });
  }
  if (agents.length) {
    out.push({
      kind: "count",
      text: agents.length > 1 ? String(agents.length) : "",
    });
  }
  if (paneCount !== undefined) {
    out.push({ kind: "count", text: String(paneCount) });
  }
  return out;
}

// Current space (blue dot), agents (one icon in the most urgent agent's
// color, count when more than one), pane count (blue terminal).
export function statusAccessories(
  agents: AgentInfo[],
  paneCount: number | undefined,
  options: { current?: boolean; paneTooltip?: string } = {},
): List.Item.Accessory[] {
  const out: List.Item.Accessory[] = [];
  if (options.current) {
    out.push({
      icon: { source: Icon.CircleFilled, tintColor: Color.Blue },
      tooltip: "Current space",
    });
  }
  if (agents.length) {
    out.push({
      icon: agentIcon(worstStatus(agents)),
      text: agents.length > 1 ? String(agents.length) : undefined,
      tooltip: agents.map((a) => `${a.name}: ${a.status}`).join(", "),
    });
  }
  if (paneCount !== undefined) {
    out.push({
      icon: { source: Icon.Terminal, tintColor: Color.Blue },
      text: String(paneCount),
      tooltip: options.paneTooltip ?? `${paneCount} panes`,
    });
  }
  return out;
}

// Project tags as purple pills (#tag, "+N" for the rest).
export function tagAccessories(fit: FitResult): List.Item.Accessory[] {
  const out: List.Item.Accessory[] = fit.tags.map((tag) => ({
    tag: { value: `#${tag}`, color: Color.Purple },
  }));
  if (fit.hiddenTags.length) {
    out.push({
      tag: { value: `+${fit.hiddenTags.length}`, color: Color.Purple },
      tooltip: fit.hiddenTags.map((t) => `#${t}`).join(" "),
    });
  }
  return out;
}
