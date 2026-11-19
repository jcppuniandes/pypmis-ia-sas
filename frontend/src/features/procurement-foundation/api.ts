import { useEffect, useRef, useState } from "react";
import { ApiError, apiFetch } from "../../api/client";
import { operationalError, useOperationalCommandKeys } from "../operational-context/commands";
import { scheduleCommandOptions } from "../schedule-foundation/api";

export type ProcurementRow = Record<string, unknown>;
export type ProcurementCommand = (
  path: string,
  body: ProcurementRow,
  version?: number,
  method?: "POST" | "PUT"
) => Promise<ProcurementRow | null>;

export const procurementRoot = "/api/v1/procurement";
export const procurementProject = (id: number) => `${procurementRoot}/projects/${id}`;
export const procurementAdmin = `${procurementRoot}/admin/profiles`;
export const isRow = (value: unknown): value is ProcurementRow =>
  Boolean(value && typeof value === "object" && !Array.isArray(value));
export const rows = (value: unknown): ProcurementRow[] =>
  Array.isArray(value) ? value.filter(isRow) : isRow(value) ? rows(value.items) : [];
export const text = (value: unknown) => (typeof value === "string" || typeof value === "number" ? String(value) : "");
export const version = (row: ProcurementRow | null) =>
  Number.isSafeInteger(row?.version) && Number(row?.version) > 0 ? Number(row?.version) : undefined;

export const query = (path: string, values: Record<string, string | number | undefined>) => {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== "" && value !== undefined) params.set(key, String(value));
  });
  const search = params.toString();
  return search ? `${path}?${search}` : path;
};

export const permission = (actions: unknown, expected: string) =>
  Array.isArray(actions) && actions.some((action) => action === expected || action === `procurement.${expected}`);

export const readProcurement = (token: string, base: string, path: string, signal?: AbortSignal) =>
  apiFetch<ProcurementRow>(`${base}${path}`, { token, signal });

export function useProcurementRead(token: string, base: string, path: string | null, revision: number) {
  const [result, setResult] = useState<{
    token: string;
    base: string;
    path: string;
    revision: number;
    value: ProcurementRow | null;
    error: string;
  } | null>(null);
  useEffect(() => {
    if (path === null) return;
    const controller = new AbortController();
    const identity = { token, base, path, revision };
    readProcurement(token, base, path, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setResult({ ...identity, value, error: "" });
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setResult({ ...identity, value: null, error: operationalError(cause) });
      });
    return () => controller.abort();
  }, [token, base, path, revision]);
  const same = result?.token === token && result.base === base && result.path === path;
  const current = same && result.revision === revision;
  return {
    value: same ? result.value : null,
    error: current ? result.error : "",
    loading: path !== null && !current,
  };
}

export function useProcurementCommands(token: string, base: string, readOnly = false) {
  const keys = useOperationalCommandKeys();
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const reload = () => setRevision((value) => value + 1);
  const command: ProcurementCommand = async (path, body, rowVersion, method = "POST") => {
    if (readOnly || lock.current) return null;
    setMessage("");
    setError("");
    if (text(body.reason).trim().length < 8) {
      setError("Indique un motivo de al menos ocho caracteres.");
      return null;
    }
    lock.current = true;
    setBusy(true);
    const endpoint = `${base}${path}`;
    const fingerprint = { body, rowVersion, method };
    try {
      const result = await apiFetch<ProcurementRow>(
        endpoint,
        scheduleCommandOptions(token, keys.key(endpoint, fingerprint), body, rowVersion, method)
      );
      keys.complete(endpoint, fingerprint);
      setMessage("Operación de Procurement registrada.");
      reload();
      return result;
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 412) {
        reload();
        setError("La versión cambió. Revise los datos actualizados antes de volver a enviar.");
      } else {
        setError(operationalError(cause));
      }
      return null;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  return { busy, message, error, revision, reload, command };
}
