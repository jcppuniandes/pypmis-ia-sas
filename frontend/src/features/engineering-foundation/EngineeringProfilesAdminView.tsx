import { useState } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import {
  engineeringAdminRoot,
  isEngineeringRow,
  items,
  permission,
  recordId,
  text,
  versionOf,
  type EngineeringRow,
} from "./api";
import { Field, Input, ReadState, Reason, Records, Select, SubmitForm } from "./controls";
import { useEngineeringCommands, useEngineeringData } from "./hooks";
import { profileDraft, profilePayload, progressMethods, revisionCoding } from "./profile";
import type { EngineeringScope } from "./types";
import "../progress-foundation/progressFoundation.css";
import "./engineeringFoundation.css";

function CodeEditor({
  title,
  values,
  onChange,
}: {
  title: string;
  values: string[];
  onChange: (value: string[]) => void;
}) {
  const [code, setCode] = useState("");
  const normalized = code.trim().toUpperCase();
  return (
    <section className="engineeringCodeEntry" aria-label={title}>
      <h4>{title}</h4>
      <ul aria-label={`Códigos de ${title}`}>
        {values.map((value) => (
          <li key={value}>
            {value}{" "}
            <button
              type="button"
              aria-label={`Quitar ${value} de ${title}`}
              onClick={() => onChange(values.filter((entry) => entry !== value))}
            >
              Quitar
            </button>
          </li>
        ))}
      </ul>
      <div className="engineeringInlineFields">
        <Input label={`Agregar código de ${title}`} value={code} onChange={setCode} />
        <button
          type="button"
          disabled={!/^[A-Z][A-Z0-9_]{0,63}$/.test(normalized) || values.includes(normalized)}
          onClick={() => {
            onChange([...values, normalized]);
            setCode("");
          }}
        >
          Agregar {title}
        </button>
      </div>
    </section>
  );
}

function ProfileEditor({
  profile,
  initial,
  scope,
  onSaved,
}: {
  profile: EngineeringRow | null;
  initial: EngineeringRow;
  scope: EngineeringScope;
  onSaved: (id: string) => void;
}) {
  const [draft, setDraft] = useState(() =>
    profileDraft(profile && isEngineeringRow(profile.content_json) ? profile.content_json : initial)
  );
  const [code, setCode] = useState(text(profile?.code));
  const [name, setName] = useState(text(profile?.name));
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [labelCode, setLabelCode] = useState("");
  const [labelText, setLabelText] = useState("");
  const update = <K extends keyof typeof draft>(key: K, value: (typeof draft)[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));
  const status = text(profile?.status).toUpperCase();
  const version = versionOf(profile);
  const editable = scope.can("admin.configure") && (!profile || (status === "DRAFT" && version !== undefined));
  const path = profile ? `/${recordId(profile)}` : "";
  async function save() {
    setError("");
    if (!editable) return;
    let payload;
    try {
      payload = profilePayload(draft);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Perfil inválido.");
      return;
    }
    const row = await scope.command(
      path,
      { ...(profile ? {} : { code: code.trim() }), name: name.trim(), content_json: payload, reason: reason.trim() },
      version,
      profile ? "PUT" : "POST"
    );
    if (row) onSaved(recordId(row));
  }
  async function transition(action: "publish" | "successor") {
    if (version === undefined) return;
    const row = await scope.command(`${path}/${action}`, { reason: reason.trim() }, version);
    if (row) {
      setReason("");
      onSaved(recordId(row));
    }
  }
  const checkbox = (label: string, key: "inherit" | "requireCheck" | "requireDocument" | "independentReleaser") => (
    <label className="progressCheck">
      <input type="checkbox" checked={draft[key]} onChange={(e) => update(key, e.target.checked)} />
      {label}
    </label>
  );
  return (
    <section className="progressPanel" aria-label="Perfil Engineering seleccionado">
      <h3>
        {profile
          ? `${text(profile.code)} · ${status} · r${text(profile.revision)}`
          : "Nuevo perfil Engineering · DRAFT"}
      </h3>
      {status === "PUBLISHED" ? (
        <p className="engineeringReadOnly">
          Perfil publicado e inmutable. Configure un sucesor para cambiar sus reglas.
        </p>
      ) : null}
      {error ? (
        <p className="progressError" role="alert">
          {error}
        </p>
      ) : null}
      <SubmitForm onSubmit={save} disabled={!editable || scope.busy}>
        <Input
          label="Código del perfil Engineering"
          value={code}
          onChange={setCode}
          required
          disabled={Boolean(profile)}
        />
        <Input label="Nombre del perfil Engineering" value={name} onChange={setName} required />
        <Select
          label="Ámbito del perfil"
          value={draft.scopeType}
          onChange={(value) => update("scopeType", value)}
          values={["tenant", "workspace"]}
          required
        />
        {draft.scopeType === "workspace" ? (
          <Input
            label="ID Workspace del perfil"
            value={draft.workspaceId}
            onChange={(value) => update("workspaceId", value)}
            type="number"
            required
          />
        ) : null}
        <Input
          label="Vigente desde UTC"
          value={draft.from}
          onChange={(value) => update("from", value)}
          type="datetime-local"
        />
        <Input
          label="Vigente hasta UTC"
          value={draft.to}
          onChange={(value) => update("to", value)}
          type="datetime-local"
        />
        {checkbox("Heredar a descendientes", "inherit")}
        <div className="progressWide engineeringProfileCodes">
          <CodeEditor title="tipos de entregable" values={draft.types} onChange={(value) => update("types", value)} />
          <CodeEditor
            title="disciplinas"
            values={draft.disciplines}
            onChange={(value) => update("disciplines", value)}
          />
          <CodeEditor
            title="propósitos de emisión"
            values={draft.purposes}
            onChange={(value) => update("purposes", value)}
          />
        </div>
        <Select
          label="Codificación de revisiones"
          value={draft.revisionRule}
          onChange={(value) => update("revisionRule", value)}
          values={revisionCoding}
          required
        />
        <Select
          label="Método de evidencia para Progress"
          value={draft.progressMethod}
          onChange={(value) => update("progressMethod", value)}
          values={progressMethods}
          required
        />
        <Input
          label="Horizonte Engineering (días)"
          value={draft.horizon}
          onChange={(value) => update("horizon", value)}
          type="number"
          required
        />
        <Input
          label="Vigencia máxima de evidencia (días)"
          value={draft.maxAge}
          onChange={(value) => update("maxAge", value)}
          type="number"
        />
        <div className="progressWide engineeringProfileCodes" aria-label="Reglas de revisión e IFC">
          {checkbox("Exigir verificación técnica", "requireCheck")}
          {checkbox("Exigir documento antes de enviar", "requireDocument")}
          {checkbox("Separar aprobador y liberador IFC", "independentReleaser")}
          <Field label="Propósitos elegibles para IFC">
            <select
              aria-label="Propósitos elegibles para IFC"
              multiple
              size={Math.min(Math.max(draft.purposes.length, 2), 5)}
              value={draft.releasePurposes}
              onChange={(e) =>
                update(
                  "releasePurposes",
                  [...e.target.selectedOptions].map((option) => option.value)
                )
              }
            >
              {draft.purposes.map((purpose) => (
                <option value={purpose} key={purpose}>
                  {purpose}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="progressWide engineeringCodeEntry">
          <h4>Etiquetas de estado</h4>
          <ul>
            {draft.labels.map((entry) => (
              <li key={entry.code}>
                {entry.code}: {entry.label}
                <button
                  type="button"
                  aria-label={`Quitar etiqueta ${entry.code}`}
                  onClick={() =>
                    update(
                      "labels",
                      draft.labels.filter((item) => item.code !== entry.code)
                    )
                  }
                >
                  Quitar
                </button>
              </li>
            ))}
          </ul>
          <div className="engineeringInlineFields">
            <Input label="Código de estado" value={labelCode} onChange={setLabelCode} />
            <Input label="Etiqueta de estado" value={labelText} onChange={setLabelText} />
            <button
              type="button"
              disabled={!/^[A-Z][A-Z0-9_]{0,63}$/.test(labelCode.trim().toUpperCase()) || !labelText.trim()}
              onClick={() => {
                const code = labelCode.trim().toUpperCase();
                update("labels", [
                  ...draft.labels.filter((entry) => entry.code !== code),
                  { code, label: labelText.trim() },
                ]);
                setLabelCode("");
                setLabelText("");
              }}
            >
              Agregar etiqueta
            </button>
          </div>
        </div>
        {editable ? (
          <>
            <Reason label="Motivo del perfil Engineering" value={reason} onChange={setReason} />
            <button type="submit">{profile ? "Guardar perfil Engineering" : "Crear perfil Engineering"}</button>
          </>
        ) : null}
      </SubmitForm>
      {profile &&
      version !== undefined &&
      ((status === "DRAFT" && scope.can("admin.publish")) ||
        (status === "PUBLISHED" && scope.can("admin.configure"))) ? (
        <SubmitForm onSubmit={() => transition(status === "DRAFT" ? "publish" : "successor")} disabled={scope.busy}>
          <Reason label="Motivo de publicación o sucesión" value={reason} onChange={setReason} />
          <button type="submit">
            {status === "DRAFT" ? "Publicar perfil Engineering" : "Crear sucesor del perfil Engineering"}
          </button>
        </SubmitForm>
      ) : null}
    </section>
  );
}

export default function EngineeringProfilesAdminView({ token }: { token: string }) {
  const [selected, setSelected] = useState<string | null>(null);
  const scope = useEngineeringCommands(token, engineeringAdminRoot);
  const profileList = useEngineeringData(token, engineeringAdminRoot, "", scope.refreshKey);
  const profiles = items(profileList.value);
  const defaults = isEngineeringRow(profileList.value?.default_content) ? profileList.value.default_content : null;
  const can = (action: string) => permission(profileList.value?.allowed_actions, action);
  const picked = profiles.find((row) => recordId(row) === selected) ?? null;
  const showEditor = defaults && (picked || (selected === "" && can("admin.configure")));
  return (
    <section
      className="progressFoundation engineeringFoundation"
      aria-label="Engineering Profiles ADMIN"
      aria-busy={scope.busy || profileList.loading}
    >
      <CompactModuleHeader
        eyebrow="ADMIN MODE · O2A ENGINEERING"
        title="Engineering Profiles"
        description="Catálogos, revisión, liberación IFC y evidencia. Publicar un perfil no opera entregables."
        metrics={[{ label: "Perfiles", value: profiles.length }]}
      />
      <ReadState {...profileList} reload={scope.reload} />
      {scope.error ? (
        <p className="progressError" role="alert">
          {scope.error}
        </p>
      ) : null}
      {scope.notice ? (
        <p className="progressNotice" role="status">
          {scope.notice}
        </p>
      ) : null}
      {!profileList.error && profileList.value ? (
        <section className="progressPanel">
          {can("admin.configure") ? (
            <button type="button" onClick={() => setSelected("")}>
              Nuevo perfil Engineering
            </button>
          ) : null}
          <Records
            label="Perfiles Engineering"
            items={profiles}
            columns={[
              ["code", "Código"],
              ["name", "Nombre"],
              ["revision", "Revisión"],
              ["status", "Estado"],
            ]}
            select={(row) => setSelected(recordId(row))}
          />
        </section>
      ) : null}
      {showEditor ? (
        <ProfileEditor
          key={picked ? `${recordId(picked)}-${text(picked.version)}` : "new"}
          profile={picked}
          initial={defaults}
          scope={{ ...scope, can, token, base: engineeringAdminRoot, busy: scope.busy || profileList.loading }}
          onSaved={(id) => {
            if (id) setSelected(id);
          }}
        />
      ) : null}
    </section>
  );
}
