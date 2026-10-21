import { useRef } from "react";

export function operationalError(error: unknown) {
  if (!(error instanceof Error)) return "No se pudo completar la operación.";
  try {
    const parsed = JSON.parse(error.message) as { detail?: unknown };
    return typeof parsed.detail === "string" ? parsed.detail : JSON.stringify(parsed.detail ?? parsed);
  } catch {
    return error.message;
  }
}

// A failed network retry with the same command/payload keeps its original key.
export function useOperationalCommandKeys() {
  const keys = useRef(new Map<string, string>());
  return {
    key: (name: string, payload: unknown) => {
      const fingerprint = JSON.stringify([name, payload]);
      const existing = keys.current.get(fingerprint);
      if (existing) return existing;
      const key = crypto.randomUUID();
      keys.current.set(fingerprint, key);
      return key;
    },
    complete: (name: string, payload: unknown) => keys.current.delete(JSON.stringify([name, payload])),
  };
}
