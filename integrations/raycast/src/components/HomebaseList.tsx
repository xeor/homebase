import { Action, ActionPanel, Color, Icon, List } from "@raycast/api";
import { useMemo, useState } from "react";
import { getConfig } from "../lib/config";
import { herdrRunning, panesByProject, projectRoots } from "../lib/herdr";
import { useHerdr, useProjects } from "../lib/hooks";
import {
  completeTag,
  filterItems,
  parseQuery,
  tagCounts,
  tagSuggestions,
} from "../lib/query";
import { agentRows, openRows } from "../lib/rows";
import {
  Scope,
  SCOPE_PLACEHOLDER,
  ScopeActions,
  ScopeDropdown,
  useScope,
} from "./scope";
import {
  AgentItem,
  NEW_SPACE_ITEMS,
  NewSpaceItem,
  OpenItem,
  ProjectItem,
} from "./items";

// The Homebase list. With `scope` the list is fixed to it (no dropdown), for
// commands that show one kind of item.
export function HomebaseList({ scope: fixedScope }: { scope?: Scope }) {
  const config = useMemo(getConfig, []);
  const projectsState = useProjects(config);
  const herdrState = useHerdr(config);
  const [pickedScope, setPickedScope] = useScope();
  const scope = fixedScope ?? pickedScope;
  const [searchText, setSearchText] = useState("");
  const filter = fixedScope
    ? undefined
    : { scope, onChange: setPickedScope, searchEmpty: !searchText };
  const query = useMemo(() => parseQuery(searchText), [searchText]);
  const { projects } = projectsState;
  const refresh = () => void projectsState.reload(true);

  const roots = useMemo(
    () => projectRoots(projects.map((p) => p.path)),
    [projects],
  );
  const projectsByPath = useMemo(
    () => new Map(projects.map((p) => [p.path, p])),
    [projects],
  );
  const openPanes = useMemo(
    () => panesByProject(herdrState, roots),
    [herdrState, roots],
  );

  const showAgents = scope === "all" || scope === "agents";
  const showOpen = scope === "all" || scope === "open";
  const showProjects = scope === "all" || scope === "projects";

  const agents = useMemo(
    () =>
      showAgents
        ? filterItems(agentRows(herdrState, roots, projectsByPath), query)
        : [],
    [showAgents, herdrState, roots, projectsByPath, query],
  );
  const allOpen = useMemo(
    () => openRows(herdrState, projects, openPanes),
    [herdrState, projects, openPanes],
  );
  const open = useMemo(
    () => (showOpen ? filterItems(allOpen, query) : []),
    [showOpen, allOpen, query],
  );
  // In All, projects already shown as an open space are not repeated.
  const listedProjects = useMemo(() => {
    if (!showProjects) {
      return [];
    }
    const shown =
      scope === "all"
        ? new Set(allOpen.map((row) => row.project?.path))
        : new Set<string>();
    return filterItems(
      projects.filter((p) => !shown.has(p.path)),
      query,
    );
  }, [showProjects, scope, allOpen, projects, query]);
  const newSpaceItems =
    showProjects && !query.tagTerms.length
      ? filterItems(NEW_SPACE_ITEMS, query)
      : [];
  const counts = useMemo(() => tagCounts(projects), [projects]);
  const suggestions = useMemo(
    () => tagSuggestions(query, counts),
    [query, counts],
  );

  return (
    <List
      isLoading={projectsState.isLoading}
      filtering={false}
      searchText={searchText}
      onSearchTextChange={setSearchText}
      searchBarPlaceholder={SCOPE_PLACEHOLDER[scope]}
      searchBarAccessory={
        fixedScope ? undefined : (
          <ScopeDropdown scope={scope} onChange={setPickedScope} />
        )
      }
      actions={
        <ActionPanel>
          <Action
            icon={Icon.ArrowClockwise}
            title="Refresh"
            onAction={refresh}
          />
          {filter ? <ScopeActions {...filter} /> : null}
        </ActionPanel>
      }
    >
      {projectsState.error ? (
        <List.EmptyView
          icon={Icon.Warning}
          title="b project list failed"
          description={projectsState.error}
        />
      ) : (
        <List.EmptyView
          icon={Icon.MagnifyingGlass}
          title="Nothing found"
          description={herdrRunning() ? undefined : "herdr is not running"}
        />
      )}
      {suggestions.length ? (
        <List.Section title="Tags" subtitle="Enter completes">
          {suggestions.map((s) => (
            <List.Item
              key={`tag:${s.tag}`}
              icon={{ source: Icon.Tag, tintColor: Color.Purple }}
              title={`${query.typingTag?.prefix ?? "#"}${s.tag}`}
              accessories={[{ text: String(s.count) }]}
              actions={
                <ActionPanel>
                  <Action
                    icon={Icon.Tag}
                    title="Complete Tag"
                    onAction={() =>
                      setSearchText(completeTag(searchText, query, s.tag))
                    }
                  />
                  {filter ? <ScopeActions {...filter} /> : null}
                </ActionPanel>
              }
            />
          ))}
        </List.Section>
      ) : null}
      {agents.length ? (
        <List.Section title="Agents" subtitle={String(agents.length)}>
          {agents.map((row) => (
            <AgentItem
              key={row.key}
              config={config}
              onRefresh={refresh}
              filter={filter}
              row={row}
            />
          ))}
        </List.Section>
      ) : null}
      {open.length ? (
        <List.Section title="Open" subtitle={String(open.length)}>
          {open.map((row) => (
            <OpenItem
              key={row.key}
              config={config}
              onRefresh={refresh}
              filter={filter}
              row={row}
            />
          ))}
        </List.Section>
      ) : null}
      {newSpaceItems.length || listedProjects.length ? (
        <List.Section title="Projects">
          {projectsState.error
            ? null
            : newSpaceItems.map((item) => (
                <NewSpaceItem
                  key={item.key}
                  config={config}
                  item={item}
                  filter={filter}
                />
              ))}
          {listedProjects.map((project) => (
            <ProjectItem
              key={project.id}
              config={config}
              onRefresh={refresh}
              filter={filter}
              project={project}
              panes={openPanes.get(project.path)}
            />
          ))}
        </List.Section>
      ) : null}
    </List>
  );
}
