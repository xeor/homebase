import { Action, ActionPanel, Color, Icon, List } from "@raycast/api";
import { ScopeActions, ScopeControl } from "./scope";
import { Config, runAction } from "../lib/config";
import { fitRow } from "../lib/fit";
import { focusPane, focusWorkspace, ProjectPanes } from "../lib/herdr";
import { goToHerdr, newSpaceWithB, openProject } from "../lib/open";
import { Project, runProjectAction } from "../lib/projects";
import { AgentRow, OpenRow } from "../lib/rows";
import {
  agentIcon,
  statusAccessories,
  statusMarkers,
  tagAccessories,
} from "../lib/status";

// filter: the filter actions, on every row so their shortcuts always work.
type Common = {
  config: Config;
  onRefresh: () => void;
  filter?: ScopeControl;
};

function RefreshAction({ onRefresh }: { onRefresh: () => void }) {
  return (
    <Action
      icon={Icon.ArrowClockwise}
      title="Refresh"
      shortcut={{ modifiers: ["cmd"], key: "r" }}
      onAction={onRefresh}
    />
  );
}

// ⌘↵ new space plus the project's b actions (Homebase action config).
function ProjectExtraActions({
  config,
  project,
  panes,
}: {
  config: Config;
  project: Project;
  panes: ProjectPanes | undefined;
}) {
  return (
    <>
      {config.openWith === "herdr" && panes ? (
        <Action
          icon={Icon.Plus}
          title="Open in New Space"
          shortcut={{ modifiers: ["cmd"], key: "return" }}
          onAction={() => openProject(config, project, panes, true)}
        />
      ) : null}
      {project.actions
        .filter((action) => action.id !== "open_selected")
        .map((action) => (
          <Action
            key={action.id}
            icon={Icon.Gear}
            title={action.title}
            onAction={() =>
              runAction(action.title, () =>
                runProjectAction(config, action, project),
              )
            }
          />
        ))}
    </>
  );
}

export function AgentItem({
  config,
  onRefresh,
  filter,
  row,
}: Common & { row: AgentRow }) {
  return (
    <List.Item
      icon={agentIcon(row.status)}
      title={row.title}
      subtitle={row.subtitle}
      keywords={row.keywords}
      accessories={[
        {
          icon: Icon.AppWindow,
          text: row.space,
          tooltip: `${row.pane.agent}: ${row.status}`,
        },
      ]}
      actions={
        <ActionPanel>
          <Action
            icon={Icon.Terminal}
            title="Go to Agent"
            onAction={() =>
              goToHerdr(config, (herdr) => focusPane(herdr, row.pane))
            }
          />
          <RefreshAction onRefresh={onRefresh} />
          {filter ? <ScopeActions {...filter} /> : null}
        </ActionPanel>
      }
    />
  );
}

export function OpenItem({
  config,
  onRefresh,
  filter,
  row,
}: Common & { row: OpenRow }) {
  const ws = row.workspace;
  const fit = fitRow({
    title: row.title,
    subtitle: row.subtitle ?? "",
    tags: row.tags,
    markers: statusMarkers(row.agents, ws.pane_count, ws.focused),
  });
  return (
    <List.Item
      icon={{
        source: row.project ? Icon.Folder : Icon.AppWindow,
        tintColor: ws.focused ? Color.Blue : undefined,
      }}
      title={fit.title}
      subtitle={fit.subtitle}
      keywords={row.keywords}
      accessories={[
        ...tagAccessories(fit),
        ...statusAccessories(row.agents, ws.pane_count ?? 0, {
          current: ws.focused,
        }),
      ]}
      actions={
        <ActionPanel>
          <ActionPanel.Section>
            <Action
              icon={Icon.Terminal}
              title="Go to Space"
              onAction={() =>
                goToHerdr(config, (herdr) =>
                  focusWorkspace(herdr, ws.workspace_id),
                )
              }
            />
            {row.project ? (
              <ProjectExtraActions
                config={config}
                project={row.project}
                panes={row.panes}
              />
            ) : null}
          </ActionPanel.Section>
          <RefreshAction onRefresh={onRefresh} />
          {filter ? <ScopeActions {...filter} /> : null}
        </ActionPanel>
      }
    />
  );
}

export function ProjectItem({
  config,
  onRefresh,
  filter,
  project,
  panes,
}: Common & { project: Project; panes: ProjectPanes | undefined }) {
  const agents = panes?.agents ?? [];
  const fit = fitRow({
    title: project.title,
    subtitle: project.subtitle ?? "",
    tags: project.tags,
    markers: statusMarkers(agents, panes?.panes.length),
  });
  return (
    <List.Item
      icon={Icon.Folder}
      title={fit.title}
      subtitle={fit.subtitle}
      keywords={project.keywords}
      accessories={[
        ...tagAccessories(fit),
        ...statusAccessories(agents, panes?.panes.length, {
          paneTooltip: panes
            ? `Open in herdr: ${panes.workspaces.join(", ")} (${panes.panes.length} panes)`
            : undefined,
        }),
      ]}
      actions={
        <ActionPanel>
          <ActionPanel.Section>
            <Action
              icon={Icon.Terminal}
              title={
                panes && config.openWith === "herdr" ? "Go to Space" : "Open"
              }
              onAction={() => openProject(config, project, panes)}
            />
            <ProjectExtraActions
              config={config}
              project={project}
              panes={panes}
            />
          </ActionPanel.Section>
          <RefreshAction onRefresh={onRefresh} />
          {filter ? <ScopeActions {...filter} /> : null}
        </ActionPanel>
      }
    />
  );
}

// The items that open a new space running b, searchable like projects.
export const NEW_SPACE_ITEMS = [
  {
    key: "find-space",
    title: "Find Space with b",
    subtitle: "new herdr space, b picker",
    actionTitle: "Open Space with B Picker",
    icon: Icon.MagnifyingGlass,
    keywords: ["open", "find", "space", "herdr", "b"],
    tags: [],
    command: (config: Config) => config.newSpaceCommand,
  },
  {
    key: "new-project",
    title: "New Project with b",
    subtitle: "new herdr space, b new-project popup",
    actionTitle: "Create Project in New Space",
    icon: Icon.Plus,
    keywords: ["new", "create", "project", "space", "herdr", "b"],
    tags: [],
    command: (config: Config) => config.newProjectCommand,
  },
];

export function NewSpaceItem({
  config,
  item,
  filter,
}: {
  config: Config;
  item: (typeof NEW_SPACE_ITEMS)[number];
  filter?: ScopeControl;
}) {
  return (
    <List.Item
      icon={{ source: item.icon, tintColor: Color.Blue }}
      title={item.title}
      subtitle={item.subtitle}
      keywords={item.keywords}
      actions={
        <ActionPanel>
          <Action
            icon={item.icon}
            title={item.actionTitle}
            onAction={() => newSpaceWithB(config, item.command(config))}
          />
          {filter ? <ScopeActions {...filter} /> : null}
        </ActionPanel>
      }
    />
  );
}
