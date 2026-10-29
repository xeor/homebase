// The filter (search bar dropdown, ⌘P): which sections the list shows.
// Switch with ⌥1-4, ⌥←/⌥→, or plain ←/→ while the search box is empty.
import { Action, ActionPanel, Cache, Icon, Keyboard, List } from "@raycast/api";
import { useCallback, useState } from "react";

export const SCOPES = [
  { value: "all", title: "All", icon: Icon.List },
  { value: "agents", title: "Agents", icon: Icon.Stars },
  { value: "open", title: "Open", icon: Icon.AppWindow },
  { value: "projects", title: "Projects", icon: Icon.Folder },
] as const;
export type Scope = (typeof SCOPES)[number]["value"];

export const SCOPE_PLACEHOLDER: Record<Scope, string> = {
  all: "Search agents, open spaces, projects, #tag",
  agents: "Search agents, #tag",
  open: "Search open spaces, #tag, -#tag",
  projects: "Search projects, #tag, -#tag",
};

const CACHE_KEY = "scope";
const cache = new Cache();
const NUMBER_KEYS = ["1", "2", "3", "4"] as const;

function isScope(value: string | undefined): value is Scope {
  return SCOPES.some((s) => s.value === value);
}

// The picked filter, remembered across launches.
export function useScope(): [Scope, (scope: Scope) => void] {
  const [scope, setState] = useState<Scope>(() => {
    const stored = cache.get(CACHE_KEY);
    return isScope(stored) ? stored : "all";
  });
  const setScope = useCallback((next: Scope) => {
    cache.set(CACHE_KEY, next);
    setState(next);
  }, []);
  return [scope, setScope];
}

function stepScope(scope: Scope, step: number): Scope {
  const index = SCOPES.findIndex((s) => s.value === scope);
  return SCOPES[(index + step + SCOPES.length) % SCOPES.length].value;
}

export function ScopeDropdown({
  scope,
  onChange,
}: {
  scope: Scope;
  onChange: (scope: Scope) => void;
}) {
  return (
    <List.Dropdown
      tooltip="Show (⌥1-4, ⌥←/⌥→)"
      value={scope}
      onChange={(value) => isScope(value) && onChange(value)}
    >
      {SCOPES.map((s) => (
        <List.Dropdown.Item
          key={s.value}
          value={s.value}
          title={s.title}
          icon={s.icon}
        />
      ))}
    </List.Dropdown>
  );
}

function StepAction({
  title,
  icon,
  shortcut,
  onAction,
}: {
  title: string;
  icon: Icon;
  shortcut: Keyboard.Shortcut;
  onAction: () => void;
}) {
  return (
    <Action icon={icon} title={title} shortcut={shortcut} onAction={onAction} />
  );
}

export type ScopeControl = {
  scope: Scope;
  onChange: (scope: Scope) => void;
  searchEmpty: boolean;
};

// Actions on every row, so the shortcuts work wherever the selection is.
export function ScopeActions({ scope, onChange, searchEmpty }: ScopeControl) {
  const next = () => onChange(stepScope(scope, 1));
  const previous = () => onChange(stepScope(scope, -1));
  return (
    <ActionPanel.Section title="Filter">
      <StepAction
        title="Next Filter"
        icon={Icon.ArrowRight}
        shortcut={{ modifiers: ["opt"], key: "arrowRight" }}
        onAction={next}
      />
      <StepAction
        title="Previous Filter"
        icon={Icon.ArrowLeft}
        shortcut={{ modifiers: ["opt"], key: "arrowLeft" }}
        onAction={previous}
      />
      {searchEmpty ? (
        <>
          <StepAction
            title="Next Filter"
            icon={Icon.ArrowRight}
            shortcut={{ modifiers: [], key: "arrowRight" }}
            onAction={next}
          />
          <StepAction
            title="Previous Filter"
            icon={Icon.ArrowLeft}
            shortcut={{ modifiers: [], key: "arrowLeft" }}
            onAction={previous}
          />
        </>
      ) : null}
      {SCOPES.map((s, index) => (
        <Action
          key={s.value}
          icon={s.icon}
          title={`Show ${s.title}`}
          shortcut={{ modifiers: ["opt"], key: NUMBER_KEYS[index] }}
          onAction={() => onChange(s.value)}
        />
      ))}
    </ActionPanel.Section>
  );
}
