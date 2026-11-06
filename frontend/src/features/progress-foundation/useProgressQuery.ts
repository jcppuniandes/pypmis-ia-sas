import { useEffect, useState } from "react";
import { operationalError } from "../operational-context/commands";
import type { ProgressPanelProps, ProgressRow } from "./types";

export function useProgressQuery(path: string | null, query: ProgressPanelProps["query"], refreshKey: unknown) {
  const [state, setState] = useState<{ path: string | null; result: ProgressRow | null; error: string }>({
    path: null,
    result: null,
    error: "",
  });
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    if (path)
      query(path)
        .then((result) => active && setState({ path, result, error: "" }))
        .catch((caught) => active && setState({ path, result: null, error: operationalError(caught) }));
    return () => {
      active = false;
    };
  }, [path, query, refreshKey, refresh]);
  return {
    result: path && state.path === path ? state.result : null,
    error: path && state.path === path ? state.error : "",
    reload: () => setRefresh((current) => current + 1),
  };
}
