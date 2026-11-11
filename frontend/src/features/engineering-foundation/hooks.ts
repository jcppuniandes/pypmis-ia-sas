import { useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client";
import { operationalError, useOperationalCommandKeys } from "../operational-context/commands";
import { engineeringRead, engineeringWrite, type EngineeringCommand, type EngineeringRow } from "./api";

export function useEngineeringData(token: string, base: string, path: string | null, refreshKey: number) {
  const [state, setState] = useState<{
    token: string;
    base: string;
    path: string;
    refreshKey: number;
    value: EngineeringRow | null;
    error: string;
  } | null>(null);
  useEffect(() => {
    if (path === null) return;
    const controller = new AbortController();
    const scope = { token, base, path, refreshKey };
    engineeringRead(token, base, path, controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setState({ ...scope, value, error: "" });
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) setState({ ...scope, value: null, error: operationalError(cause) });
      });
    return () => controller.abort();
  }, [token, base, path, refreshKey]);
  const sameScope = state?.token === token && state.base === base && state.path === path;
  return {
    value: sameScope ? state.value : null,
    error: sameScope && state.refreshKey === refreshKey ? state.error : "",
    loading: path !== null && (!sameScope || state.refreshKey !== refreshKey),
  };
}

export function useEngineeringCommands(token: string, base: string, readOnly = false) {
  const keys = useOperationalCommandKeys();
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const reload = () => setRefreshKey((current) => current + 1);
  const command: EngineeringCommand = async (path, payload, version, method = "POST") => {
    if (readOnly || lock.current) return null;
    setError("");
    setNotice("");
    if (typeof payload.reason !== "string" || payload.reason.trim().length < 8) {
      setError("Indique un motivo de al menos ocho caracteres.");
      return null;
    }
    lock.current = true;
    setBusy(true);
    const fingerprint = { base, path, payload, version, method };
    const name = `${base}${path}`;
    try {
      const result = await engineeringWrite(token, base, path, payload, keys.key(name, fingerprint), version, method);
      keys.complete(name, fingerprint);
      reload();
      setNotice("Operación de Ingeniería registrada.");
      return result;
    } catch (cause) {
      const stale = cause instanceof ApiError && cause.status === 412;
      if (stale) reload();
      setError(
        stale
          ? "La versión cambió. Se actualizó la lectura; revise la revisión antes de volver a enviar."
          : operationalError(cause)
      );
      return null;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  return { command, busy, error, notice, refreshKey, reload };
}
