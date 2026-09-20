import { useCallback, useEffect, useState } from "react";

import "./App.css";

import { AppShell } from "./components/AppShell";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { GrafiSplash } from "./components/GrafiSplash";
import { StartupScreen } from "./components/StartupScreen";
import { WindowCloseButton } from "./components/WindowCloseButton";

import { fetchBootstrap } from "./ipc/client";

import { formatUserError, parseErrorCode } from "./ipc/errors";
import { setupMainWindowCloseRequestListener } from "./utils/mainWindowClose";

import type { AppLoadState, DashboardProject } from "./ipc/types";

function mapError(err: unknown): AppLoadState {
  const raw = err instanceof Error ? err.message : String(err);
  const { code } = parseErrorCode(raw);
  const message = formatUserError(err);

  if (code === "backend_unavailable" || raw.includes("backend_unavailable")) {
    return {
      status: "error",
      title: "Backend unavailable",
      message,
      code: "backend_unavailable",
    };
  }
  if (code === "config_error") {
    return {
      status: "error",
      title: "Configuration problem",
      message,
      code: "config_error",
    };
  }
  if (code === "database_error") {
    return {
      status: "error",
      title: "Database problem",
      message,
      code: "database_error",
    };
  }
  return {
    status: "error",
    title: "Startup failed",
    message,
    code: code === "unknown" ? "unknown" : code,
  };
}

export default function App() {
  const [state, setState] = useState<AppLoadState>({ status: "loading" });
  const [splashKey, setSplashKey] = useState(0);
  const [splashDone, setSplashDone] = useState(false);

  const load = useCallback(async () => {
    setSplashKey((key) => key + 1);
    setSplashDone(false);
    setState({ status: "loading" });
    try {
      const bootstrap = await fetchBootstrap();
      setState({ status: "ready", bootstrap });
    } catch (err) {
      setState(mapError(err));
    }
  }, []);

  const handleProjectAdded = useCallback((project: DashboardProject) => {
    setState((prev) => {
      if (prev.status !== "ready") {
        return prev;
      }
      const exists = prev.bootstrap.projects.some((p) => p.id === project.id);
      const projects = exists
        ? prev.bootstrap.projects.map((p) => (p.id === project.id ? project : p))
        : [...prev.bootstrap.projects, project];
      return {
        status: "ready",
        bootstrap: {
          ...prev.bootstrap,
          projects,
        },
      };
    });
  }, []);

  const handleProjectsReordered = useCallback((projects: DashboardProject[]) => {
    setState((prev) => {
      if (prev.status !== "ready") {
        return prev;
      }
      return {
        status: "ready",
        bootstrap: {
          ...prev.bootstrap,
          projects,
        },
      };
    });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    void setupMainWindowCloseRequestListener().then((dispose) => {
      unlisten = dispose;
    });
    return () => {
      unlisten?.();
    };
  }, []);

  const handleProjectRemoved = useCallback((projectId: number) => {
    setState((prev) => {
      if (prev.status !== "ready") {
        return prev;
      }
      return {
        status: "ready",
        bootstrap: {
          ...prev.bootstrap,
          projects: prev.bootstrap.projects.filter((p) => p.id !== projectId),
        },
      };
    });
  }, []);

  const showApp = splashDone && state.status !== "loading";

  return (
    <ErrorBoundary onRetry={() => void load()}>
      <WindowCloseButton />
      <GrafiSplash
        key={splashKey}
        visible={state.status === "loading"}
        message="Waking up"
        onHidden={() => setSplashDone(true)}
      />
      {showApp && state.status === "ready" ? (
        <AppShell
          state={state}
          onProjectAdded={handleProjectAdded}
          onProjectRemoved={handleProjectRemoved}
          onProjectsReordered={handleProjectsReordered}
        />
      ) : null}
      {showApp && state.status === "error" ? (
        <div className="app-shell app-shell--centered">
          <StartupScreen
            errorTitle={state.title}
            errorMessage={state.message}
            onRetry={() => void load()}
          />
        </div>
      ) : null}
    </ErrorBoundary>
  );
}
