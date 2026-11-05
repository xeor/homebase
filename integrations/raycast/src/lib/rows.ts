// List rows built from herdr state plus the project list.
import path from "node:path";
import {
  HerdrPane,
  HerdrState,
  HerdrWorkspace,
  projectRoot,
  ProjectPanes,
  workspaceLabel,
} from "./herdr";
import { Project } from "./projects";
import { Searchable } from "./query";
import { AgentInfo, agentRank } from "./status";

export type AgentRow = Searchable & {
  key: string;
  pane: HerdrPane;
  status: string;
  space: string;
  order: number;
};

// A herdr space, with the project it holds (if any).
export type OpenRow = Searchable & {
  key: string;
  workspace: HerdrWorkspace;
  project?: Project;
  panes?: ProjectPanes;
  agents: AgentInfo[];
};

function agentInfo(pane: HerdrPane): AgentInfo {
  return {
    name: pane.agent ?? "agent",
    status: pane.agent_status || "unknown",
  };
}

// One row per coding agent, most urgent first, titled by its project (else
// its space). Carries the project's tags so `#tag` finds it.
export function agentRows(
  state: HerdrState,
  roots: string[],
  projectsByPath: Map<string, Project>,
): AgentRow[] {
  const spaces = new Map(state.workspaces.map((w) => [w.workspace_id, w]));
  return state.panes
    .filter((pane) => pane.agent)
    .map((pane) => {
      const workspace = spaces.get(pane.workspace_id);
      const space = workspace ? workspaceLabel(workspace) : pane.workspace_id;
      const root = projectRoot(pane, roots);
      const project = root ? projectsByPath.get(root) : undefined;
      const { name, status } = agentInfo(pane);
      const subtitle = pane.terminal_title_stripped?.trim();
      return {
        key: pane.pane_id,
        title: project?.title ?? (root ? path.basename(root) : space),
        ...(subtitle ? { subtitle } : {}),
        keywords: ["agent", name, status, space],
        tags: project?.tags ?? [],
        pane,
        status,
        space,
        order: workspace?.number ?? 0,
      };
    })
    .sort(
      (a, b) => agentRank(a.status) - agentRank(b.status) || a.order - b.order,
    );
}

// The project a space holds: one named like the space, else the one with the
// most panes in it.
function spaceProject(
  workspace: HerdrWorkspace,
  projects: Project[],
  openPanes: Map<string, ProjectPanes>,
): Project | undefined {
  const label = workspaceLabel(workspace);
  const named = projects.find((p) => p.title === label);
  if (named) {
    return named;
  }
  let best: { project: Project; count: number } | undefined;
  for (const project of projects) {
    const count =
      openPanes
        .get(project.path)
        ?.panes.filter((p) => p.workspace_id === workspace.workspace_id)
        .length ?? 0;
    if (count && (!best || count > best.count)) {
      best = { project, count };
    }
  }
  return best?.project;
}

// Every herdr space in order, with its project's subtitle, tags and keywords.
export function openRows(
  state: HerdrState,
  projects: Project[],
  openPanes: Map<string, ProjectPanes>,
): OpenRow[] {
  return [...state.workspaces]
    .sort((a, b) => (a.number ?? 0) - (b.number ?? 0))
    .map((workspace) => {
      const project = spaceProject(workspace, projects, openPanes);
      const agents = state.panes
        .filter((p) => p.agent && p.workspace_id === workspace.workspace_id)
        .map(agentInfo);
      return {
        key: workspace.workspace_id,
        title: workspaceLabel(workspace),
        ...(project?.subtitle ? { subtitle: project.subtitle } : {}),
        keywords: [
          "space",
          "herdr",
          ...(project ? [project.title, ...project.keywords] : []),
        ],
        tags: project?.tags ?? [],
        workspace,
        ...(project ? { project, panes: openPanes.get(project.path) } : {}),
        agents,
      };
    });
}
