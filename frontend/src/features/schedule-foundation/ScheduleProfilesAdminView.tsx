import { useEffect, useState, type FormEvent } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { operationalError, useOperationalCommandKeys } from "../operational-context/commands";
import { scheduleApi } from "./api";
import type { ScheduleProfile } from "./types";
import "./scheduleFoundation.css";

export default function ScheduleProfilesAdminView({ token }: { token: string }) {
  const [profiles, setProfiles] = useState<ScheduleProfile[]>([]);
  const [defaults, setDefaults] = useState<Record<string, unknown>>({});
  const [allowed, setAllowed] = useState<string[]>([]);
  const [selected, setSelected] = useState<ScheduleProfile | null>(null);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [content, setContent] = useState("{}");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
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
    scheduleApi
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
      const result = await scheduleApi.profileCommand(
        token,
        path,
        payload,
        keys.key(path, fingerprint),
        version,
        method
      );
      keys.complete(path, fingerprint);
      const next = await scheduleApi.profiles(token);
      setProfiles(next.items);
      setAllowed(next.allowed_actions);
      setDefaults(next.default_content);
      select(next.items.find((profile) => profile.id === result.id) ?? result, next.default_content);
      setMessage("Schedule Profile registrado. Publicar configuración no acepta Current ni aprueba Baseline.");
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
    <section className="scheduleFoundation" aria-label="Schedule Profiles ADMIN" aria-busy={busy || loading}>
      <CompactModuleHeader
        title="Schedule Profiles"
        eyebrow="ADMIN MODE · SCHEDULE FOUNDATION"
        description="Tipos, calendarios, políticas de mapeo, calidad, float importado y separación de funciones."
        metrics={[
          { label: "Draft", value: profiles.filter((profile) => profile.status.toUpperCase() === "DRAFT").length },
          {
            label: "Published",
            value: profiles.filter((profile) => profile.status.toUpperCase() === "PUBLISHED").length,
          },
        ]}
      />
      {loading ? <p role="status">Cargando Schedule Profiles…</p> : null}
      {error ? (
        <p role="alert" className="scheduleError">
          {error}
        </p>
      ) : null}
      {message ? (
        <p role="status" className="scheduleNotice">
          {message}
        </p>
      ) : null}
      <p className="scheduleBoundary">
        ADMIN gobierna tipos de Schedule y Baseline, near-critical threshold, open ends, lags, restricciones, duración,
        calendarios, mapeos, subconjunto P6 y SoD. USER opera versiones. No se introduce motor CPM local ni permiso de
        compromiso.
      </p>
      {canConfigure ? (
        <button disabled={busy} type="button" onClick={() => select(null)}>
          Nuevo Schedule Profile
        </button>
      ) : null}
      <div className="scheduleTable">
        <table aria-label="Schedule Profiles">
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
                    Ver Schedule Profile {profile.code}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canConfigure || selected ? (
        <section className="schedulePanel">
          <h3>{selected ? `${selected.code} · r${selected.revision}` : "Nuevo Schedule Profile · DRAFT"}</h3>
          <form onSubmit={save} className="scheduleForm">
            <label>
              Schedule Profile Code
              <input
                required
                disabled={Boolean(selected) || !editable || busy}
                value={code}
                onChange={(event) => setCode(event.target.value)}
              />
            </label>
            <label>
              Schedule Profile Name
              <input
                required
                disabled={!editable || busy}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="scheduleWide">
              Schedule Profile configuration JSON
              <textarea
                aria-label="Schedule Profile configuration JSON"
                rows={24}
                spellCheck={false}
                disabled={!editable || busy}
                value={content}
                onChange={(event) => setContent(event.target.value)}
              />
            </label>
            {editable ? (
              <button disabled={busy} type="submit">
                {selected ? "Guardar Schedule Profile borrador" : "Crear Schedule Profile DRAFT"}
              </button>
            ) : null}
          </form>
          {selected ? (
            <div className="scheduleActions">
              <label className="scheduleControl">
                Motivo Schedule Profile
                <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
              </label>
              {canPublish && selected.status.toUpperCase() === "DRAFT" ? (
                <button
                  disabled={busy || reason.trim().length < 8}
                  type="button"
                  onClick={() => void run(`/${selected.id}/publish`, { reason }, selected.version)}
                >
                  Publicar Schedule Profile
                </button>
              ) : null}
              {canConfigure && selected.status.toUpperCase() === "PUBLISHED" ? (
                <button
                  disabled={busy || reason.trim().length < 8}
                  type="button"
                  onClick={() => void run(`/${selected.id}/successor`, { reason }, selected.version)}
                >
                  Crear Schedule Profile sucesor
                </button>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
