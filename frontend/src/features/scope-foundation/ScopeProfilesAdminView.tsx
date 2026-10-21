import { useEffect, useState, type FormEvent } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { operationalError, useOperationalCommandKeys } from "../operational-context/commands";
import { scopeApi } from "./api";
import type { ScopeProfile } from "./types";
import "./scopeFoundation.css";

export default function ScopeProfilesAdminView({ token }: { token: string }) {
  const [profiles, setProfiles] = useState<ScopeProfile[]>([]);
  const [defaults, setDefaults] = useState<Record<string, unknown>>({});
  const [allowed, setAllowed] = useState<string[]>([]);
  const [selected, setSelected] = useState<ScopeProfile | null>(null);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [content, setContent] = useState("{}");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const keys = useOperationalCommandKeys();
  function select(profile: ScopeProfile | null, initial = defaults) {
    setSelected(profile);
    setCode(profile?.code ?? "");
    setName(profile?.name ?? "");
    setContent(JSON.stringify(profile?.content_json ?? initial, null, 2));
  }
  useEffect(() => {
    let active = true;
    scopeApi
      .profiles(token)
      .then((result) => {
        if (!active) return;
        setProfiles(result.items);
        setAllowed(result.allowed_actions);
        setDefaults(result.default_content);
        setContent(JSON.stringify(result.default_content, null, 2));
      })
      .catch((caught) => active && setError(operationalError(caught)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [token]);
  async function run(path: string, payload: unknown, version?: number, method = "POST") {
    setBusy(true);
    setError("");
    setMessage("");
    const fingerprint = { path, payload, version, method };
    try {
      const result = await scopeApi.profileCommand(token, path, payload, keys.key(path, fingerprint), version, method);
      keys.complete(path, fingerprint);
      const next = await scopeApi.profiles(token);
      setProfiles(next.items);
      setAllowed(next.allowed_actions);
      setDefaults(next.default_content);
      select(next.items.find((profile) => profile.id === result.id) ?? result, next.default_content);
      setMessage("Configuración Scope registrada. Las publicaciones son inmutables.");
    } catch (caught) {
      setError(operationalError(caught));
    } finally {
      setBusy(false);
    }
  }
  function save(event: FormEvent) {
    event.preventDefault();
    try {
      const parsed: unknown = JSON.parse(content);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error("La configuración debe ser un objeto JSON.");
      void run(
        selected ? `/${selected.id}` : "",
        { ...(selected ? {} : { code }), name, content_json: parsed },
        selected?.version,
        selected ? "PUT" : "POST"
      );
    } catch (caught) {
      setError(operationalError(caught));
    }
  }
  const canConfigure = allowed.includes("admin.configure");
  const canPublish = allowed.includes("admin.publish");
  const editable = canConfigure && (!selected || selected.status.toUpperCase() === "DRAFT");
  return (
    <section className="scopeFoundation" aria-label="Scope Profiles ADMIN" aria-busy={busy || loading}>
      <CompactModuleHeader
        eyebrow="ADMIN MODE · SCOPE FOUNDATION"
        title="Scope Profiles"
        description="Catálogos, unidades, plantillas, reglas de aprobación, segmentación y separación de funciones."
        metrics={[
          { label: "Draft", value: profiles.filter((profile) => profile.status.toUpperCase() === "DRAFT").length },
          {
            label: "Published",
            value: profiles.filter((profile) => profile.status.toUpperCase() === "PUBLISHED").length,
          },
        ]}
      />
      {loading ? <p role="status">Cargando configuración Scope…</p> : null}
      {error ? (
        <p role="alert" className="scopeError">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="scopeNotice">
          {message}
        </p>
      ) : null}
      <p className="scopeBoundary">
        ADMIN configura Scope Nature, Scope Types, disciplinas, unidades, plantillas Excel/IFC, workflows, tolerancias y
        SoD. USER importa y opera en el proyecto canónico; cambiar configuración no aprueba Scope ni concede compromiso.
      </p>
      {canConfigure ? (
        <button type="button" disabled={busy} onClick={() => select(null)}>
          Nuevo Scope Profile
        </button>
      ) : null}
      <div className="scopeTable">
        <table aria-label="Scope Profiles">
          <thead>
            <tr>
              <th>Código</th>
              <th>Nombre</th>
              <th>Revisión</th>
              <th>Estado</th>
              <th>Detalle</th>
            </tr>
          </thead>
          <tbody>
            {profiles.map((profile) => (
              <tr key={profile.id}>
                <td>{profile.code}</td>
                <td>{profile.name}</td>
                <td>{profile.revision}</td>
                <td>{profile.status.toUpperCase()}</td>
                <td>
                  <button type="button" onClick={() => select(profile)}>
                    Ver Scope Profile {profile.code}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canConfigure || selected ? (
        <section className="scopePanel">
          <h3>{selected ? `${selected.code} · r${selected.revision}` : "Nuevo Scope Profile · DRAFT"}</h3>
          <form onSubmit={save} className="scopeForm">
            <label>
              Scope Profile Code
              <input
                required
                disabled={Boolean(selected) || !editable || busy}
                value={code}
                onChange={(event) => setCode(event.target.value)}
              />
            </label>
            <label>
              Scope Profile Name
              <input
                required
                disabled={!editable || busy}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="scopeWide">
              Scope Profile configuration JSON
              <textarea
                rows={22}
                spellCheck={false}
                disabled={!editable || busy}
                value={content}
                onChange={(event) => setContent(event.target.value)}
              />
            </label>
            {editable ? (
              <button type="submit" disabled={busy}>
                {selected ? "Guardar Scope Profile borrador" : "Crear Scope Profile DRAFT"}
              </button>
            ) : null}
          </form>
          {selected ? (
            <div className="scopeActions">
              <label>
                Motivo Scope Profile
                <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
              </label>
              {canPublish && selected.status.toUpperCase() === "DRAFT" ? (
                <button
                  type="button"
                  disabled={busy || reason.trim().length < 8}
                  onClick={() => void run(`/${selected.id}/publish`, { reason }, selected.version)}
                >
                  Publicar Scope Profile
                </button>
              ) : null}
              {canConfigure && selected.status.toUpperCase() === "PUBLISHED" ? (
                <button
                  type="button"
                  disabled={busy || reason.trim().length < 8}
                  onClick={() => void run(`/${selected.id}/successor`, { reason }, selected.version)}
                >
                  Crear Scope Profile sucesor
                </button>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
