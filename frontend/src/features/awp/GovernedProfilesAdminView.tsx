import { useEffect, useState, type FormEvent } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { operationalError, useOperationalCommandKeys } from "../operational-context/commands";
import type { ScheduleProfile } from "../schedule-foundation/types";
import { governedProfilesApi } from "./api";
import { Field } from "./Fields";
import "./awp.css";

export default function GovernedProfilesAdminView({ token, kind }: { token: string; kind: "awp" | "4d" }) {
  const title = kind === "awp" ? "AWP Profiles" : "4D State Profiles";
  const root = kind === "awp" ? "/api/v1/awp/admin/profiles" : "/api/v1/schedule/4d/admin/profiles";
  const [profiles, setProfiles] = useState<ScheduleProfile[]>([]);
  const [defaults, setDefaults] = useState<Record<string, unknown>>({});
  const [allowed, setAllowed] = useState<string[]>([]);
  const [selected, setSelected] = useState<ScheduleProfile | null>(null);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [content, setContent] = useState("{}");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const keys = useOperationalCommandKeys();
  function select(profile: ScheduleProfile | null, initial = defaults) {
    setSelected(profile);
    setCode(profile?.code ?? "");
    setName(profile?.name ?? "");
    setContent(JSON.stringify(profile?.content_json ?? initial, null, 2));
  }
  useEffect(() => {
    let active = true;
    governedProfilesApi
      .list(token, root)
      .then((result) => {
        if (active) {
          setProfiles(result.items);
          setDefaults(result.default_content);
          setContent(JSON.stringify(result.default_content, null, 2));
          setAllowed(result.allowed_actions);
        }
      })
      .catch((caught) => active && setError(operationalError(caught)));
    return () => {
      active = false;
    };
  }, [token, root]);
  async function run(path: string, payload: unknown, version?: number, method = "POST") {
    setBusy(true);
    setError("");
    setMessage("");
    const fingerprint = { root, path, payload, version, method };
    try {
      const result = await governedProfilesApi.command(
        token,
        root,
        path,
        payload,
        keys.key(`${root}${path}`, fingerprint),
        version,
        method
      );
      keys.complete(`${root}${path}`, fingerprint);
      const next = await governedProfilesApi.list(token, root);
      setProfiles(next.items);
      setAllowed(next.allowed_actions);
      setDefaults(next.default_content);
      select(next.items.find((row) => row.id === result.id) ?? result, next.default_content);
      setMessage(`${title} registrado. La publicación es independiente y no cambia fuentes históricas.`);
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
        throw new Error("El perfil debe ser un objeto JSON.");
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
    <section className="awpWorkspace" aria-label={`${title} ADMIN`} aria-busy={busy}>
      <CompactModuleHeader
        title={title}
        eyebrow="ADMIN MODE · AWP / READINESS / 4D"
        tone="admin"
        description={
          kind === "awp"
            ? "CWA, tipos de paquete y dependencia, constraints, requisitos de readiness y release independiente."
            : "Reglas semánticas de Scope Nature, presentación y completitud de mappings. Las fechas proceden de Schedule."
        }
        metrics={[{ label: "Profiles", value: profiles.length }]}
      />
      {error ? (
        <p role="alert" className="awpError">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="awpNotice">
          {message}
        </p>
      ) : null}
      {canConfigure ? (
        <button type="button" onClick={() => select(null)}>
          Nuevo {title}
        </button>
      ) : null}
      <div className="awpTable">
        <table aria-label={title}>
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
                    Ver {title} {profile.code}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canConfigure || selected ? (
        <section className="awpPanel">
          <h3>{selected ? `${selected.code} · r${selected.revision}` : `Nuevo ${title} · DRAFT`}</h3>
          <form className="awpForm" onSubmit={save}>
            <Field label={`${title} Code`}>
              <input
                aria-label={`${title} Code`}
                required
                disabled={Boolean(selected) || !editable || busy}
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
            </Field>
            <Field label={`${title} Name`}>
              <input
                aria-label={`${title} Name`}
                required
                disabled={!editable || busy}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </Field>
            <label className="awpField awpWide">
              <span>{title} configuration JSON</span>
              <textarea
                aria-label={`${title} configuration JSON`}
                rows={25}
                spellCheck={false}
                disabled={!editable || busy}
                value={content}
                onChange={(e) => setContent(e.target.value)}
              />
            </label>
            {editable ? (
              <button type="submit" disabled={busy}>
                {selected ? `Guardar ${title} borrador` : `Crear ${title} DRAFT`}
              </button>
            ) : null}
          </form>
          {selected ? (
            <div className="awpForm">
              <Field label={`Motivo ${title}`}>
                <input
                  aria-label={`Motivo ${title}`}
                  minLength={8}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </Field>
              {canPublish && selected.status.toUpperCase() === "DRAFT" ? (
                <button
                  type="button"
                  disabled={busy || reason.trim().length < 8}
                  onClick={() => void run(`/${selected.id}/publish`, { reason }, selected.version)}
                >
                  Publicar {title}
                </button>
              ) : null}
              {canConfigure && selected.status.toUpperCase() === "PUBLISHED" ? (
                <button
                  type="button"
                  disabled={busy || reason.trim().length < 8}
                  onClick={() => void run(`/${selected.id}/successor`, { reason }, selected.version)}
                >
                  Crear {title} sucesor
                </button>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
