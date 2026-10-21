import { useEffect, useState, type FormEvent } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { operationalApi } from "./api";
import { operationalError, useOperationalCommandKeys } from "./commands";
import type { OperationalProfile } from "./types";
import "./operationalContext.css";

export default function OperationalProfilesAdminView({ token }: { token: string }) {
  const [profiles, setProfiles] = useState<OperationalProfile[]>([]);
  const [defaults, setDefaults] = useState<Record<string, unknown>>({});
  const [allowedActions, setAllowedActions] = useState<string[]>([]);
  const [selected, setSelected] = useState<OperationalProfile | null>(null);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [content, setContent] = useState("{}");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const keys = useOperationalCommandKeys();

  useEffect(() => {
    let active = true;
    operationalApi
      .profiles(token)
      .then((result) => {
        if (!active) return;
        setProfiles(result.items);
        setDefaults(result.default_content);
        setContent(JSON.stringify(result.default_content, null, 2));
        setAllowedActions(result.allowed_actions);
      })
      .catch((caught: unknown) => active && setError(operationalError(caught)))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [token]);

  function selectProfile(profile: OperationalProfile | null) {
    setSelected(profile);
    setCode(profile?.code ?? "");
    setName(profile?.name ?? "");
    setContent(JSON.stringify(profile?.content_json ?? defaults, null, 2));
    setError("");
  }

  async function run(action: string, payload: unknown, task: (key: string) => Promise<OperationalProfile>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await task(keys.key(action, payload));
      keys.complete(action, payload);
      const next = await operationalApi.profiles(token);
      setProfiles(next.items);
      setAllowedActions(next.allowed_actions);
      setDefaults(next.default_content);
      selectProfile(next.items.find((item) => item.id === result.id) ?? result);
      setMessage(action === "publish" ? "Perfil publicado; esta revisión es inmutable." : "Configuración registrada.");
    } catch (caught) {
      setError(operationalError(caught));
    } finally {
      setBusy(false);
    }
  }

  function save(event: FormEvent) {
    event.preventDefault();
    let contentJson: Record<string, unknown>;
    try {
      const parsed: unknown = JSON.parse(content);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error("El contenido debe ser un objeto JSON.");
      contentJson = parsed as Record<string, unknown>;
    } catch (caught) {
      setError(operationalError(caught));
      return;
    }
    const draft = { code, name, content_json: contentJson };
    void run("save", { id: selected?.id, version: selected?.version, ...draft }, (key) =>
      selected
        ? operationalApi.updateProfile(token, selected, { name, content_json: contentJson }, key)
        : operationalApi.createProfile(token, draft, key)
    );
  }

  function transition(action: "publish" | "successor") {
    if (!selected) return;
    void run(action, { id: selected.id, version: selected.version, reason }, (key) =>
      operationalApi.profileCommand(token, selected, action, reason, key)
    );
  }

  const canConfigure = allowedActions.includes("admin.configure");
  const canPublish = allowedActions.includes("admin.publish");
  const editable = canConfigure && (!selected || selected.status === "DRAFT");

  return (
    <section className="operationalFoundation" aria-label="Operational Profiles ADMIN" aria-busy={busy || loading}>
      <CompactModuleHeader
        eyebrow="ADMIN MODE · PROJECT CONTROLS FOUNDATION"
        title="Operational Profiles"
        description="Aplicabilidad, calendario, vinculación y reglas comunes reutilizables; no configuración operacional del usuario."
        metrics={[
          { label: "Draft", value: profiles.filter((item) => item.status === "DRAFT").length },
          { label: "Published", value: profiles.filter((item) => item.status === "PUBLISHED").length },
        ]}
      />
      {loading ? <p role="status">Cargando perfiles autorizados…</p> : null}
      {error ? (
        <p className="operationalNotice error" role="alert">
          {error}
        </p>
      ) : null}
      {message ? (
        <p className="operationalNotice" role="status">
          {message}
        </p>
      ) : null}
      {!loading && !canConfigure ? (
        <p className="operationalBoundary">
          Configuración restringida a ADMIN. La autorización se valida en cada comando del servidor.
        </p>
      ) : null}
      <section className="operationalSection">
        <div className="operationalSectionTitle">
          <h3>Revisiones e historia de políticas</h3>
          {canConfigure ? (
            <button disabled={busy} onClick={() => selectProfile(null)} type="button">
              Nuevo perfil
            </button>
          ) : null}
        </div>
        <div className="operationalTableScroll">
          <table>
            <thead>
              <tr>
                <th>Código</th>
                <th>Nombre</th>
                <th>Revisión</th>
                <th>Estado</th>
                <th>Vigencia</th>
                <th>Detalle</th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((profile) => (
                <tr key={profile.id}>
                  <td>{profile.code}</td>
                  <td>{profile.name}</td>
                  <td>{profile.revision}</td>
                  <td>{profile.status}</td>
                  <td>
                    {String(profile.content_json.effective_from ?? "—")}
                    <small>{String(profile.content_json.effective_to ?? "Sin fin declarado")}</small>
                  </td>
                  <td>
                    <button
                      disabled={busy}
                      onClick={() => selectProfile(profile)}
                      type="button"
                      aria-label={`Ver perfil ${profile.code} revisión ${profile.revision}`}
                    >
                      Ver revisión
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {canConfigure || selected ? (
        <section className="operationalSection">
          <h3>{selected ? `${selected.code} · r${selected.revision} · ${selected.status}` : "Nuevo perfil · DRAFT"}</h3>
          <p>
            El contenido usa el contrato validado del servidor: modelos de gobierno, Project Type, alcance heredable,
            vigencia, cadencia, zona, cutoff, referencias de gobierno y SoD. Publicar no habilita O1B/O1C.
          </p>
          <form className="operationalForm" onSubmit={save}>
            <label>
              Código del perfil
              <input
                required
                disabled={busy || Boolean(selected) || !editable}
                value={code}
                onChange={(event) => setCode(event.target.value)}
              />
            </label>
            <label>
              Nombre del perfil
              <input
                required
                disabled={busy || !editable}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label className="operationalFullWidth">
              Configuración del perfil (JSON)
              <textarea
                required
                spellCheck={false}
                rows={18}
                disabled={busy || !editable}
                value={content}
                onChange={(event) => setContent(event.target.value)}
              />
            </label>
            {editable ? (
              <button disabled={busy} type="submit">
                {selected ? "Guardar borrador" : "Crear perfil DRAFT"}
              </button>
            ) : null}
          </form>
          {selected ? (
            <div className="operationalProfileCommands">
              <label>
                Motivo de publicación / sucesor
                <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
              </label>
              {selected.status === "DRAFT" && canPublish ? (
                <button disabled={busy || reason.trim().length < 8} onClick={() => transition("publish")} type="button">
                  Publicar perfil
                </button>
              ) : null}
              {selected.status === "PUBLISHED" && canConfigure ? (
                <button
                  disabled={busy || reason.trim().length < 8}
                  onClick={() => transition("successor")}
                  type="button"
                >
                  Crear sucesor DRAFT
                </button>
              ) : null}
              {selected.status === "PUBLISHED" ? (
                <p>Revisión publicada inmutable. Los periodos históricos conservan su revisión original.</p>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
