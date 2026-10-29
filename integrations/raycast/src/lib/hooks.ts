import { showToast, Toast } from "@raycast/api";
import { useCallback, useEffect, useRef, useState } from "react";
import { Config, errorMessage, herdrFor } from "./config";
import { HerdrState, loadState } from "./herdr";
import { Project, projectsFromB, readSnapshot } from "./projects";

// The daemon rewrites the snapshot at least every minute; older means it is not running.
const SNAPSHOT_STALE_S = 180;
// Agent states and spaces refresh this often while the list is open.
const HERDR_POLL_MS = 2_000;

const EMPTY_HERDR: HerdrState = { panes: [], workspaces: [] };

export type ProjectsState = {
  error?: string;
  isLoading: boolean;
  projects: Project[];
};

// Projects from the daemon snapshot; `reload(true)` asks b directly.
export function useProjects(config: Config) {
  const requestId = useRef(0);
  const [state, setState] = useState<ProjectsState>({
    isLoading: true,
    projects: [],
  });

  const reload = useCallback(
    async (fromB = false) => {
      const id = requestId.current + 1;
      requestId.current = id;
      setState((current) => ({
        ...current,
        error: undefined,
        isLoading: true,
      }));

      // Fast path: the daemon's snapshot file, no b process.
      const snapshot = fromB ? undefined : await readSnapshot(config);
      if (snapshot && id === requestId.current) {
        const fresh = snapshot.ageS < SNAPSHOT_STALE_S;
        setState({ isLoading: !fresh, projects: snapshot.projects });
        if (fresh) {
          return;
        }
      }

      try {
        const projects = await projectsFromB(config);
        if (id === requestId.current) {
          setState({ isLoading: false, projects });
        }
      } catch (error) {
        if (id !== requestId.current) {
          return;
        }
        const message = errorMessage(error);
        setState((current) => ({
          error: current.projects.length ? undefined : message,
          isLoading: false,
          projects: current.projects,
        }));
        await showToast({
          style: Toast.Style.Failure,
          title: "b project list failed",
          message,
        });
      }
    },
    [config],
  );

  useEffect(() => {
    void reload();
  }, [reload]);

  return { ...state, reload };
}

// herdr panes and spaces, polled while the command is open.
export function useHerdr(config: Config): HerdrState {
  const [state, setState] = useState<HerdrState>(EMPTY_HERDR);

  useEffect(() => {
    const load = async () => {
      const herdr = herdrFor(config);
      if (!herdr) {
        setState(EMPTY_HERDR);
        return;
      }
      try {
        setState(await loadState(herdr));
      } catch (error) {
        console.error(`herdr state: ${errorMessage(error)}`);
      }
    };
    void load();
    const timer = setInterval(() => void load(), HERDR_POLL_MS);
    return () => clearInterval(timer);
  }, [config]);

  return state;
}
