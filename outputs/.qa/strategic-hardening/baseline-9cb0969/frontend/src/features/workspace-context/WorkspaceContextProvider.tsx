import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { workspaceContextApi } from "./api";
import type { WorkspaceContext, WorkspaceHome } from "./types";

type WorkspaceContextValue = {
  context: WorkspaceContext | null;
  home: WorkspaceHome | null;
  loading: boolean;
  error: string;
  reload: () => Promise<void>;
};

const ActiveWorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceContextProvider({
  children,
  route,
  token,
  workspaceId,
}: {
  children: ReactNode;
  route: string;
  token: string;
  workspaceId: number;
}) {
  return (
    <WorkspaceContextLoader key={`${token}:${workspaceId}`} route={route} token={token} workspaceId={workspaceId}>
      {children}
    </WorkspaceContextLoader>
  );
}

function WorkspaceContextLoader({
  children,
  route,
  token,
  workspaceId,
}: {
  children: ReactNode;
  route: string;
  token: string;
  workspaceId: number;
}) {
  const [context, setContext] = useState<WorkspaceContext | null>(null);
  const [home, setHome] = useState<WorkspaceHome | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const initialRoute = useRef(route);

  const load = useCallback(async () => {
    const currentGeneration = ++generation.current;
    setLoading(true);
    setError("");
    try {
      const [nextContext, nextHome] = await Promise.all([
        workspaceContextApi.open(token, workspaceId, initialRoute.current),
        workspaceContextApi.home(token, workspaceId),
      ]);
      if (generation.current !== currentGeneration) return;
      setContext(nextContext);
      setHome(nextHome);
    } catch (caught) {
      if (generation.current !== currentGeneration) return;
      setError(caught instanceof Error ? caught.message : "No fue posible cargar el Workspace Context.");
    } finally {
      if (generation.current === currentGeneration) setLoading(false);
    }
  }, [token, workspaceId]);

  useEffect(() => {
    queueMicrotask(() => void load());
    return () => {
      generation.current += 1;
    };
  }, [load]);

  const value = useMemo(() => ({ context, home, loading, error, reload: load }), [context, error, home, load, loading]);
  return <ActiveWorkspaceContext.Provider value={value}>{children}</ActiveWorkspaceContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useActiveWorkspaceContext() {
  const value = useContext(ActiveWorkspaceContext);
  if (!value) throw new Error("useActiveWorkspaceContext requires WorkspaceContextProvider");
  return value;
}
