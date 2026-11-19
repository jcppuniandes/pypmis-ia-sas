import { useState, type FormEvent } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { Evidence, Field, Input, Records } from "../progress-foundation/Fields";
import { isRow, permits, profilesRoot, rows, text, useCommands, useRead, versionOf, type Row } from "./api";
import { CommandForm, ReadState } from "./ContractForms";
import "../progress-foundation/progressFoundation.css";
import "./contractsFoundation.css";

const labels: Record<string, string> = {
  contract_types: "Tipos de contrato",
  commercial_models: "Modelos comerciales",
  contract_statuses: "Estados de contrato",
  change_types: "Tipos de cambio",
  application_statuses: "Estados de solicitud",
  certificate_statuses: "Estados de certificado",
  notice_types: "Tipos de aviso",
  claim_types: "Tipos de reclamación",
  retention_rules: "Reglas de retención",
  commitment_policy: "Política de compromisos",
  separation_of_duties: "Separación de funciones",
  approval_thresholds: "Umbrales de aprobación",
  readiness_requirements: "Requisitos de preparación",
  currency: "Monedas",
  currencies: "Monedas",
  scope: "Ámbito del perfil",
  inherit_to_descendants: "Heredar a descendientes",
  effective_from: "Vigente desde (ISO 8601)",
  effective_to: "Vigente hasta (ISO 8601)",
};

function ProfileForm({
  base,
  record,
  busy,
  submit,
}: {
  base: Row;
  record?: Row;
  busy: boolean;
  submit: (body: Row) => Promise<Row | null>;
}) {
  const [code, setCode] = useState(text(record?.code));
  const [name, setName] = useState(text(record?.name));
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [settings, setSettings] = useState<Row>(base);
  const [raw, setRaw] = useState<Record<string, string>>({});
  const label = record ? "Guardar borrador contractual" : "Crear borrador contractual";
  async function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const content = { ...settings };
      for (const [key, value] of Object.entries(raw)) {
        const parsed: unknown = JSON.parse(value);
        if (!isRow(parsed) && !Array.isArray(parsed))
          throw new Error(`${labels[key] ?? key}: use un objeto o una lista JSON.`);
        content[key] = parsed;
      }
      const result = await submit({
        ...(record ? {} : { code: code.trim() }),
        name: name.trim(),
        content_json: content,
        reason: reason.trim(),
      });
      if (result) setReason("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Configuración inválida.");
    }
  }
  return (
    <form aria-label={label} onSubmit={(event) => void save(event)}>
      <fieldset className="progressForm contractFieldset" disabled={busy}>
        {!record ? <Input label="Código del perfil contractual" value={code} onChange={setCode} required /> : null}
        <Input label="Nombre del perfil contractual" value={name} onChange={setName} required />
        {Object.entries(settings)
          .filter(([key]) => key in labels)
          .map(([key, value]) => {
            const title = labels[key];
            if (typeof value === "boolean")
              return (
                <Field key={key} label={title}>
                  <input
                    type="checkbox"
                    aria-label={title}
                    checked={value}
                    onChange={(e) => setSettings((old) => ({ ...old, [key]: e.target.checked }))}
                  />
                </Field>
              );
            if (key === "effective_from" || key === "effective_to")
              return (
                <Input
                  key={key}
                  label={title}
                  value={text(value)}
                  onChange={(next) => setSettings((old) => ({ ...old, [key]: next || null }))}
                />
              );
            if (typeof value === "string" || typeof value === "number")
              return (
                <Input
                  key={key}
                  label={title}
                  value={String(value)}
                  type={typeof value === "number" ? "number" : "text"}
                  onChange={(next) =>
                    setSettings((old) => ({ ...old, [key]: typeof value === "number" ? Number(next) : next }))
                  }
                  required
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
        <Field label="Motivo del perfil contractual">
          <input
            aria-label="Motivo del perfil contractual"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            minLength={8}
            maxLength={1000}
            required
          />
        </Field>
        {error ? (
          <p role="alert" className="progressError">
            {error}
          </p>
        ) : null}
        <button type="submit">{label}</button>
      </fieldset>
    </form>
  );
}

export default function ContractProfilesAdminView({ token }: { token: string }) {
  const commands = useCommands(token, profilesRoot);
  const result = useRead(token, profilesRoot, "", commands.revision);
  const [selection, setSelection] = useState("");
  const [action, setAction] = useState("");
  const profile = rows(result.data).find((item) => text(item.id) === selection);
  const defaults = isRow(result.data?.default_content) ? result.data.default_content : null;
  const content = isRow(profile?.content_json) ? profile.content_json : defaults;
  const allowed = result.data?.allowed_actions;
  const mayConfigure = permits(allowed, "admin.configure");
  const mayPublish = permits(allowed, "admin.publish");
  const status = text(profile?.status).toUpperCase();
  const version = versionOf(profile?.version);
  const busy = commands.busy || result.loading;
  const show = (record: Row | null) => {
    if (record?.id !== undefined) {
      setSelection(text(record.id));
      setAction("");
    }
    return record;
  };
  return (
    <section className="progressFoundation contractsFoundation" aria-label="Contract Profiles" aria-busy={busy}>
      <CompactModuleHeader
        title="Contract Profiles"
        eyebrow="ADMIN MODE · CONTRACTS · O2C"
        tone="admin"
        description="Catálogos y políticas contractuales versionadas. Un perfil publicado no se modifica; debe crearse un sucesor."
        metrics={[{ label: "Perfiles", value: rows(result.data).length }]}
        actions={
          <button type="button" onClick={commands.reload} disabled={busy}>
            Actualizar perfiles
          </button>
        }
      />
      <ReadState {...result} retry={commands.reload} />
      {commands.error ? (
        <p className="progressError" role="alert">
          {commands.error}
        </p>
      ) : null}
      {commands.message ? (
        <p className="progressNotice" role="status">
          {commands.message}
        </p>
      ) : null}
      {result.data ? (
        <section className="progressPanel" aria-label="Registro de perfiles contractuales">
          <Records
            label="Perfiles contractuales"
            items={rows(result.data)}
            columns={[
              ["id", "ID"],
              ["code", "Código"],
              ["name", "Nombre"],
              ["revision", "Revisión"],
              ["version", "Versión de control"],
              ["status", "Estado"],
            ]}
            select={(row) => show(row)}
          />
          {mayConfigure ? (
            <button
              type="button"
              onClick={() => {
                setSelection("");
                setAction("create");
              }}
            >
              Nuevo perfil contractual
            </button>
          ) : null}
          {action === "create" && mayConfigure && defaults ? (
            <ProfileForm
              key="create"
              base={defaults}
              busy={busy}
              submit={async (body) => show(await commands.command("", body))}
            />
          ) : null}
          {profile ? (
            <section className="contractDetail" aria-label="Perfil contractual seleccionado">
              <h3>
                {text(profile.name)} · {status}
              </h3>
              {content ? <Evidence title="Configuración versionada" value={content} /> : null}
              {version !== undefined && status === "DRAFT" && mayConfigure && content ? (
                <ProfileForm
                  key={`${selection}:${version}`}
                  base={content}
                  record={profile}
                  busy={busy}
                  submit={async (body) => show(await commands.command(`/${selection}`, body, version, "PUT"))}
                />
              ) : null}
              <div className="contractActions">
                {version !== undefined && status === "DRAFT" && mayPublish ? (
                  <button type="button" disabled={busy} onClick={() => setAction("publish")}>
                    Publicar perfil…
                  </button>
                ) : null}
                {version !== undefined && status === "PUBLISHED" && mayConfigure ? (
                  <button type="button" disabled={busy} onClick={() => setAction("successor")}>
                    Crear sucesor…
                  </button>
                ) : null}
              </div>
              {version !== undefined &&
              ((action === "publish" && status === "DRAFT" && mayPublish) ||
                (action === "successor" && status === "PUBLISHED" && mayConfigure)) ? (
                <CommandForm
                  key={action}
                  label={action === "publish" ? "Publicar perfil" : "Crear sucesor"}
                  spec={{}}
                  environment={{ token, base: profilesRoot, revision: commands.revision, profile: content }}
                  busy={busy}
                  submit={async (body) => show(await commands.command(`/${selection}/${action}`, body, version))}
                />
              ) : null}
            </section>
          ) : null}
        </section>
      ) : null}
    </section>
  );
}
