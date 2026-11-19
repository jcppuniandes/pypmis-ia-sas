import { useState, type FormEvent } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { Evidence, Field, Input, Records } from "../progress-foundation/Fields";
import { isRow, permits, profilesRoot, rows, text, useCommands, useRead, versionOf, type Row } from "./api";
import { FieldCommandForm, ReadState } from "./FieldForms";
import "../progress-foundation/progressFoundation.css";
import "./fieldOperations.css";

const labels: Record<string, string> = {
  production_types: "Tipos de producción",
  installed_production_types: "Tipos de evidencia instalada",
  field_event_types: "Tipos de evento de campo",
  event_types: "Tipos de evento",
  shift_types: "Tipos de turno",
  crew_trades: "Oficios de cuadrilla",
  equipment_usage_types: "Tipos de uso de equipo",
  weather_conditions: "Condiciones meteorológicas",
  site_condition_types: "Condiciones de sitio",
  instruction_types: "Tipos de instrucción",
  constraint_observation_types: "Tipos de observación de restricciones",
  constraint_types: "Tipos de restricción",
  rework_reasons: "Motivos de retrabajo",
  approval_profiles: "Perfiles de aprobación",
  separation_of_duties: "Separación de funciones",
  sod: "Separación de funciones",
  production_policy: "Política de producción",
  iwp_policy: "Política de liberación IWP",
  allowed_non_iwp_reasons: "Excepciones no IWP",
  readiness_requirements: "Requisitos de preparación",
  scope: "Ámbito del perfil",
  inherit_to_descendants: "Heredar a descendientes",
  effective_from: "Vigente desde ISO 8601",
  effective_to: "Vigente hasta ISO 8601",
};

function ProfileForm({
  content,
  record,
  busy,
  submit,
}: {
  content: Row;
  record?: Row;
  busy: boolean;
  submit: (body: Row) => Promise<Row | null>;
}) {
  const [code, setCode] = useState(text(record?.code));
  const [name, setName] = useState(text(record?.name));
  const [reason, setReason] = useState("");
  const [values, setValues] = useState(content);
  const [raw, setRaw] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const label = record ? "Guardar borrador de campo" : "Crear borrador de campo";
  async function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const json = { ...values };
      for (const [key, value] of Object.entries(raw)) {
        const parsed: unknown = JSON.parse(value);
        if (!isRow(parsed) && !Array.isArray(parsed))
          throw new Error(`${labels[key] ?? key}: use un objeto o lista JSON.`);
        json[key] = parsed;
      }
      const result = await submit({
        ...(record ? {} : { code: code.trim() }),
        name: name.trim(),
        content_json: json,
        reason: reason.trim(),
      });
      if (result) setReason("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Perfil inválido.");
    }
  }
  return (
    <form aria-label={label} onSubmit={(event) => void save(event)}>
      <fieldset className="progressForm fieldReference" disabled={busy}>
        {!record ? <Input label="Código del perfil de campo" value={code} onChange={setCode} required /> : null}
        <Input label="Nombre del perfil de campo" value={name} onChange={setName} required />
        {Object.entries(values).map(([key, value]) => {
          const title = labels[key] ?? key.replace(/_/g, " ");
          if (typeof value === "boolean")
            return (
              <Field key={key} label={title}>
                <input
                  type="checkbox"
                  aria-label={title}
                  checked={value}
                  onChange={(event) => setValues((old) => ({ ...old, [key]: event.target.checked }))}
                />
              </Field>
            );
          if (typeof value === "string" || typeof value === "number" || value === null)
            return (
              <Input
                key={key}
                label={title}
                value={text(value)}
                type={typeof value === "number" ? "number" : "text"}
                onChange={(next) =>
                  setValues((old) => ({
                    ...old,
                    [key]: value === null ? next || null : typeof value === "number" ? Number(next) : next,
                  }))
                }
              />
            );
          return (
            <Field key={key} label={title}>
              <textarea
                aria-label={title}
                spellCheck={false}
                rows={4}
                value={raw[key] ?? JSON.stringify(value, null, 2)}
                onChange={(event) => setRaw((old) => ({ ...old, [key]: event.target.value }))}
                required
              />
            </Field>
          );
        })}
        <Field label="Motivo del perfil de campo">
          <input
            aria-label="Motivo del perfil de campo"
            minLength={8}
            maxLength={1000}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            required
          />
        </Field>
        {error ? (
          <p className="progressError" role="alert">
            {error}
          </p>
        ) : null}
        <button type="submit">{label}</button>
      </fieldset>
    </form>
  );
}

export default function FieldProfilesAdminView({ token }: { token: string }) {
  const commands = useCommands(token, profilesRoot);
  const result = useRead(token, profilesRoot, "", commands.revision);
  const [selection, setSelection] = useState("");
  const [editor, setEditor] = useState("");
  const profile = rows(result.data).find((row) => text(row.id) === selection);
  const defaults = isRow(result.data?.default_content) ? result.data.default_content : null;
  const content = isRow(profile?.content_json) ? profile.content_json : defaults;
  const version = versionOf(profile?.version);
  const status = text(profile?.status).toUpperCase();
  const canConfigure = permits(result.data?.allowed_actions, "admin.configure");
  const canPublish = permits(result.data?.allowed_actions, "admin.publish");
  const busy = commands.busy || result.loading;
  const show = (row: Row | null) => {
    if (row?.id) {
      setSelection(text(row.id));
      setEditor("");
    }
    return row;
  };
  return (
    <section className="progressFoundation fieldOperations" aria-label="Field Operations Profiles" aria-busy={busy}>
      <CompactModuleHeader
        title="Field Operations Profiles"
        eyebrow="ADMIN MODE · FIELD OPERATIONS · O3A"
        tone="admin"
        description="Catálogos y políticas de hechos de campo. Un perfil publicado conserva su revisión y se corrige con un sucesor."
        metrics={[{ label: "Perfiles", value: rows(result.data).length }]}
        actions={
          <button type="button" disabled={busy} onClick={commands.reload}>
            Actualizar perfiles
          </button>
        }
      />
      <ReadState {...result} retry={commands.reload} />
      {commands.error ? (
        <p role="alert" className="progressError">
          {commands.error}
        </p>
      ) : null}
      {commands.message ? <p role="status">{commands.message}</p> : null}
      {result.data ? (
        <section className="progressPanel">
          <Records
            label="Perfiles de campo"
            items={rows(result.data)}
            columns={[
              ["id", "ID"],
              ["code", "Código"],
              ["name", "Nombre"],
              ["revision", "Revisión"],
              ["version", "Versión"],
              ["status", "Estado"],
            ]}
            select={show}
          />
          {canConfigure ? (
            <button
              type="button"
              onClick={() => {
                setSelection("");
                setEditor("create");
              }}
            >
              Nuevo perfil de campo
            </button>
          ) : null}
          {editor === "create" && canConfigure && defaults ? (
            <ProfileForm
              key="create"
              content={defaults}
              busy={busy}
              submit={async (body) => show(await commands.command("", body))}
            />
          ) : null}
          {profile ? (
            <section className="fieldDetail" aria-label="Perfil de campo seleccionado">
              <h3>
                {text(profile.name)} · {status}
              </h3>
              <Evidence title="Configuración de campo versionada" value={content} />
              {status === "DRAFT" && canConfigure && content && version ? (
                <ProfileForm
                  key={`${selection}:${version}`}
                  content={content}
                  record={profile}
                  busy={busy}
                  submit={async (body) => show(await commands.command(`/${selection}`, body, version, "PUT"))}
                />
              ) : null}
              <div className="fieldActions">
                {status === "DRAFT" && canPublish && version ? (
                  <button type="button" onClick={() => setEditor("publish")}>
                    Publicar perfil…
                  </button>
                ) : null}
                {status === "PUBLISHED" && canConfigure && version ? (
                  <button type="button" onClick={() => setEditor("successor")}>
                    Crear sucesor…
                  </button>
                ) : null}
              </div>
              {version &&
              ((editor === "publish" && status === "DRAFT" && canPublish) ||
                (editor === "successor" && status === "PUBLISHED" && canConfigure)) ? (
                <FieldCommandForm
                  label={editor === "publish" ? "Publicar perfil" : "Crear sucesor"}
                  spec={{}}
                  busy={busy}
                  environment={{ token, base: profilesRoot, profile: content, revision: commands.revision }}
                  submit={async (body) => show(await commands.command(`/${selection}/${editor}`, body, version))}
                />
              ) : null}
            </section>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
