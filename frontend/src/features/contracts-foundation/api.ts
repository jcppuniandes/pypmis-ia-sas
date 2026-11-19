import { useEffect, useRef, useState } from "react";
import { ApiError, apiFetch } from "../../api/client";
import { operationalError, useOperationalCommandKeys } from "../operational-context/commands";
import { scheduleCommandOptions } from "../schedule-foundation/api";

export type Row = Record<string, unknown>;
export type Command = (path: string, body: Row, version?: number, method?: "POST" | "PUT") => Promise<Row | null>;
export const projectRoot = (id: number) => `/api/v1/contracts/projects/${id}`;
export const profilesRoot = "/api/v1/contracts/admin/profiles";
export const isRow = (value: unknown): value is Row =>
  Boolean(value && typeof value === "object" && !Array.isArray(value));
export const rows = (value: unknown): Row[] =>
  Array.isArray(value)
    ? value.filter(isRow)
    : isRow(value) && Array.isArray(value.items)
      ? value.items.filter(isRow)
      : [];
export const text = (value: unknown) => (typeof value === "string" || typeof value === "number" ? String(value) : "");
export const versionOf = (value: unknown, allowZero = false) =>
  Number.isSafeInteger(value) && Number(value) >= (allowZero ? 0 : 1) ? Number(value) : undefined;
export const positiveId = (value: unknown) =>
  /^\d+$/.test(text(value)) && Number.isSafeInteger(Number(value)) && Number(value) > 0;
export const query = (path: string, filters: Record<string, string | number | undefined>) => {
  const index = path.indexOf("?");
  const params = new URLSearchParams(index < 0 ? "" : path.slice(index + 1));
  for (const [key, value] of Object.entries(filters))
    if (value !== undefined && value !== "") params.set(key, String(value));
  const result = params.toString();
  const base = index < 0 ? path : path.slice(0, index);
  return result ? `${base}?${result}` : base;
};
export const permits = (actions: unknown, duty: string) =>
  Array.isArray(actions) && actions.some((value) => value === duty || value === `contracts.${duty}`);

export function useRead(token: string, base: string, path: string | null, revision: number) {
  const [state, setState] = useState<{
    token: string;
    base: string;
    path: string;
    revision: number;
    data: Row | null;
    error: string;
  } | null>(null);
  useEffect(() => {
    if (path === null) return;
    const controller = new AbortController();
    const identity = { token, base, path, revision };
    apiFetch<Row>(base + path, { token, signal: controller.signal }).then(
      (data) => {
        if (!controller.signal.aborted) setState({ ...identity, data, error: "" });
      },
      (error: unknown) => {
        if (!controller.signal.aborted) setState({ ...identity, data: null, error: operationalError(error) });
      }
    );
    return () => controller.abort();
  }, [token, base, path, revision]);
  const samePath = state?.token === token && state.base === base && state.path === path;
  const current = samePath && state.revision === revision;
  return { data: samePath ? state.data : null, error: current ? state.error : "", loading: path !== null && !current };
}

export function useCommands(token: string, base: string, readOnly = false) {
  const keys = useOperationalCommandKeys();
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0);
  const reload = () => setRevision((current) => current + 1);
  const command: Command = async (path, body, version, method = "POST") => {
    if (readOnly || lock.current) return null;
    setError("");
    setMessage("");
    if (text(body.reason).trim().length < 8) {
      setError("Indique un motivo de al menos ocho caracteres.");
      return null;
    }
    lock.current = true;
    setBusy(true);
    const endpoint = base + path;
    const fingerprint = { body, version, method };
    try {
      const data = await apiFetch<Row>(
        endpoint,
        scheduleCommandOptions(token, keys.key(endpoint, fingerprint), body, version, method)
      );
      keys.complete(endpoint, fingerprint);
      reload();
      setMessage("Operación registrada.");
      return data;
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 412) {
        reload();
        setError("La versión cambió. Revise la versión vigente y confirme nuevamente.");
      } else {
        setError(operationalError(cause));
      }
      return null;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  return { busy, error, message, revision, reload, command };
}

export type Scope = ReturnType<typeof useCommands> & {
  token: string;
  base: string;
  workspaceId: number;
  profile: Row | null;
  can: (action: string) => boolean;
};
