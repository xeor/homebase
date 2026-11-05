import { closeMainWindow, showToast, Toast } from "@raycast/api";
import {
  Config,
  errorMessage,
  herdrFor,
  runBDetached,
  runShell,
} from "./config";
import {
  bestPane,
  createSpace,
  focusPane,
  Herdr,
  ProjectPanes,
  typeCommand,
} from "./herdr";
import { Project } from "./projects";

// Bring the herdr terminal window to the front: the focus command (Hammerspoon
// pair.focusTerminal) when set, else (or when it fails) the terminal app.
async function focusTerminal(config: Config) {
  if (config.focusCommand) {
    try {
      if ((await runShell(config, config.focusCommand)) !== "false") {
        return;
      }
    } catch {
      // fall through to activating the app
    }
  }
  await runShell(config, `open -b '${config.terminalBundleId}'`).catch(
    () => undefined,
  );
}

// Run `go` against herdr, close Raycast and focus the terminal. False when
// herdr is not running or `go` failed (a toast says why).
async function withHerdr(
  config: Config,
  failTitle: string,
  go: (herdr: Herdr) => Promise<unknown>,
): Promise<boolean> {
  const herdr = herdrFor(config);
  if (!herdr) {
    await showToast({
      style: Toast.Style.Failure,
      title: "herdr is not running",
    });
    return false;
  }
  try {
    await Promise.all([go(herdr), closeMainWindow({ clearRootSearch: true })]);
    await focusTerminal(config);
    return true;
  } catch (error) {
    await showToast({
      style: Toast.Style.Failure,
      title: failTitle,
      message: errorMessage(error),
    });
    return false;
  }
}

// Focus an open herdr space or pane.
export async function goToHerdr(
  config: Config,
  go: (herdr: Herdr) => Promise<void>,
) {
  await withHerdr(config, "herdr focus failed", go);
}

// The project's herdr space (or a new one), else `b open`.
export async function openProject(
  config: Config,
  project: Project,
  panes: ProjectPanes | undefined,
  forceNew = false,
) {
  if (config.openWith !== "herdr" || !herdrFor(config)) {
    runBDetached(config, ["open", project.title]);
    await closeMainWindow({ clearRootSearch: true });
    return;
  }
  const pane = forceNew || !panes ? undefined : bestPane(panes, project.title);
  const opened = await withHerdr(config, "herdr open failed", (herdr) =>
    pane
      ? focusPane(herdr, pane)
      : createSpace(herdr, project.path, project.title),
  );
  if (!opened) {
    return;
  }
  runBDetached(config, ["integration", "raycast", "opened", project.title]);
}

// A new herdr space in the base folder running `command`: the b picker
// (same as ⌘N in herdr) or b's new-project popup.
export async function newSpaceWithB(config: Config, command: string) {
  await withHerdr(config, "new space failed", async (herdr) => {
    const paneId = await createSpace(herdr, config.baseDir);
    await typeCommand(herdr, paneId, command);
  });
}
