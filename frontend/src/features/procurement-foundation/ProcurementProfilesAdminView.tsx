import { useState, type FormEvent } from "react";
import CompactModuleHeader from "../enterprise-structure/components/CompactModuleHeader";
import { Field, Input, Records, Select } from "../progress-foundation/Fields";
import {
  isRow,
  permission,
  procurementAdmin,
  rows,
  text,
  useProcurementCommands,
  useProcurementRead,
  version,
  type ProcurementRow,
} from "./api";
import { CommandForm, ReadState } from "./Panels";
import "../progress-foundation/progressFoundation.css";
import "./procurementFoundation.css";

const catalogs = {
  procurement_types: "Tipos de compra",
  categories: "Categorías de compra",
  sourcing_methods: "Métodos de compra",
  material_categories: "Categorías de materiales",
  inspection_types: "Tipos de inspección",
  shipment_modes: "Modos de transporte",
};
const thresholds = {
  minimum_rfq_vendors: "Mínimo de proveedores RFQ",
  receipt_overage_percent: "Exceso permitido de recepción (%)",
  availability_max_age_days: "Vigencia de disponibilidad (días)",
  lookahead_days: "Horizonte Look-Ahead (días)",
};
const safeguards = {
  require_engineering_ifc: "Exigir liberación IFC de Ingeniería",
  require_technical_evaluation: "Exigir evaluación técnica",
  require_commercial_evaluation: "Exigir evaluación comercial",
  require_award_for_po: "Exigir adjudicación para emitir PO",
  require_inspection_for_acceptance: "Exigir inspección antes de aceptar material",
};
const duties = {
  requisition_preparer_cannot_approve: "Separar preparación y aprobación de requisición",
  rfq_preparer_cannot_issue: "Separar preparación y emisión de RFQ",
  technical_and_commercial_distinct: "Separar evaluadores técnico y comercial",
  evaluator_cannot_award: "Separar evaluación y adjudicación",
  po_preparer_cannot_approve: "Separar preparación y aprobación de PO",
  po_revision_preparer_cannot_approve: "Separar preparación y aprobación de revisión de PO",
  receiver_cannot_accept: "Separar recepción y aceptación de material",
  inspector_cannot_accept: "Separar inspección y aceptación de recepción",
};
const advanced = {
  status_profiles: "Perfiles de estado",
  permission_profiles: "Perfiles de permisos de referencia",
  display_labels: "Etiquetas opcionales",
};
const initialObject = (value: unknown) => JSON.stringify(isRow(value) ? value : {}, null, 2);

function Editor({
  profile,
  defaults,
  controls,
  can,
  select,
}: {
  profile: ProcurementRow | null;
  defaults: ProcurementRow;
  controls: ReturnType<typeof useProcurementCommands>;
  can: (action: string) => boolean;
  select: (id: string) => void;
}) {
  const initial = isRow(profile?.content_json) ? profile.content_json : defaults;
  const initialScope = isRow(initial.scope) ? initial.scope : {};
  const [scope, setScope] = useState(text(initialScope.type) || "tenant");
  const [workspace, setWorkspace] = useState(text(initialScope.workspace_id));
  const [code, setCode] = useState(text(profile?.code));
  const [name, setName] = useState(text(profile?.name));
  const [reason, setReason] = useState("");
  const [content, setContent] = useState<ProcurementRow>(() => ({ ...initial }));
  const [catalogText, setCatalogText] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      Object.keys(catalogs).map((key) => [
        key,
        Array.isArray(initial[key]) ? (initial[key] as unknown[]).map(text).join(", ") : "",
      ])
    )
  );
  const [advancedText, setAdvancedText] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.keys(advanced).map((key) => [key, initialObject(initial[key])]))
  );
  const [localError, setLocalError] = useState("");
  const status = text(profile?.status).toUpperCase();
  const rowVersion = version(profile);
  const path = profile ? `/${text(profile.id)}` : "";
  const editable = can("admin.configure") && (!profile || (status === "DRAFT" && rowVersion !== undefined));
  const sod = isRow(content.separation_of_duties) ? content.separation_of_duties : {};
  const update = (key: string, value: unknown) => setContent((current) => ({ ...current, [key]: value }));
  async function save(event: FormEvent) {
    event.preventDefault();
    setLocalError("");
    try {
      const workspaceId = scope === "workspace" ? Number(workspace) : null;
      if (workspaceId !== null && (!Number.isSafeInteger(workspaceId) || workspaceId < 1))
        throw new Error("Indique un ID de Workspace válido.");
      const next: ProcurementRow = { ...content, scope: { type: scope, workspace_id: workspaceId } };
      for (const [key, raw] of Object.entries(catalogText)) {
        const entries = raw
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean);
        if (
          !entries.length ||
          new Set(entries).size !== entries.length ||
          entries.some((value) => !/^[A-Z0-9][A-Z0-9_.-]{0,79}$/.test(value))
        )
          throw new Error(`Catálogo inválido: ${catalogs[key as keyof typeof catalogs]}.`);
        next[key] = entries;
      }
      for (const [key, raw] of Object.entries(advancedText)) {
        const parsed = JSON.parse(raw) as unknown;
        if (!isRow(parsed)) throw new Error("Los perfiles y etiquetas deben ser objetos JSON.");
        next[key] = parsed;
      }
      for (const key of Object.keys(thresholds)) {
        const value = Number(next[key]);
        if (!Number.isSafeInteger(value) || text(next[key]) === "")
          throw new Error("Los umbrales deben ser números enteros.");
        next[key] = value;
      }
      const row = await controls.command(
        path,
        {
          ...(profile ? {} : { code: code.trim() }),
          name: name.trim(),
          content_json: next,
          reason: reason.trim(),
        },
        rowVersion,
        profile ? "PUT" : "POST"
      );
      if (row && text(row.id)) select(text(row.id));
    } catch (cause) {
      setLocalError(cause instanceof Error ? cause.message : "Perfil no válido.");
    }
  }
  const changeStatus = status === "DRAFT" ? "publish" : "successor";
  const allowedChange = status === "DRAFT" ? can("admin.publish") : status === "PUBLISHED" && can("admin.configure");
  const checkbox = (label: string, checked: boolean, toggle: (value: boolean) => void) => (
    <label key={label} className="progressCheck">
      <input type="checkbox" checked={checked} onChange={(e) => toggle(e.target.checked)} />
      {label}
    </label>
  );
  return (
    <section className="progressPanel" aria-label="Editor de perfil Procurement">
      <h3>{profile ? `${code} · ${status} · r${text(profile.revision)}` : "Nuevo perfil Procurement"}</h3>
      {status === "PUBLISHED" ? (
        <p className="progressBoundary">Perfil publicado inmutable. Prepare un sucesor para cambiar sus reglas.</p>
      ) : null}
      <form onSubmit={(event) => void save(event)}>
        <fieldset disabled={!editable || controls.busy} className="progressForm procurementFieldset">
          <Input
            label="Código del perfil Procurement"
            value={code}
            onChange={setCode}
            required
            disabled={Boolean(profile)}
          />
          <Input label="Nombre del perfil Procurement" value={name} onChange={setName} required />
          <Select
            label="Ámbito del perfil Procurement"
            value={scope}
            onChange={setScope}
            values={["tenant", "workspace"]}
            required
          />
          {scope === "workspace" ? (
            <Input
              label="ID Workspace del perfil Procurement"
              value={workspace}
              onChange={setWorkspace}
              type="number"
              required
            />
          ) : null}
          <Input
            label="Vigencia inicial (ISO 8601 UTC)"
            value={text(content.effective_from)}
            onChange={(value) => update("effective_from", value.trim() || null)}
          />
          <Input
            label="Vigencia final (ISO 8601 UTC)"
            value={text(content.effective_to)}
            onChange={(value) => update("effective_to", value.trim() || null)}
          />
          {checkbox("Heredar a descendientes", content.inherit_to_descendants === true, (value) =>
            update("inherit_to_descendants", value)
          )}
          <h4 className="progressWide">Catálogos · códigos separados por coma</h4>
          {Object.entries(catalogs).map(([key, title]) => (
            <Input
              key={key}
              label={title}
              value={catalogText[key]}
              onChange={(value) => setCatalogText((current) => ({ ...current, [key]: value }))}
              required
            />
          ))}
          <h4 className="progressWide">Umbrales y dependencias</h4>
          {Object.entries(thresholds).map(([key, title]) => (
            <Input
              key={key}
              label={title}
              value={text(content[key])}
              onChange={(value) => update(key, value)}
              type="number"
              required
            />
          ))}
          {Object.entries(safeguards).map(([key, title]) =>
            checkbox(title, content[key] === true, (value) => update(key, value))
          )}
          <h4 className="progressWide">Separación de funciones</h4>
          {Object.entries(duties).map(([key, title]) =>
            checkbox(title, sod[key] === true, (value) => update("separation_of_duties", { ...sod, [key]: value }))
          )}
          <details className="progressWide">
            <summary>Perfiles de referencia y etiquetas</summary>
            <p>Estas referencias no conceden permisos; el servidor verifica RBAC.</p>
            {Object.entries(advanced).map(([key, title]) => (
              <Field key={key} label={title}>
                <textarea
                  aria-label={title}
                  value={advancedText[key]}
                  onChange={(e) => setAdvancedText((current) => ({ ...current, [key]: e.target.value }))}
                />
              </Field>
            ))}
          </details>
          {editable ? (
            <>
              <Field label="Motivo del perfil Procurement">
                <input
                  aria-label="Motivo del perfil Procurement"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  minLength={8}
                  required
                />
              </Field>
              <button type="submit">{profile ? "Guardar perfil Procurement" : "Crear perfil Procurement"}</button>
            </>
          ) : null}
        </fieldset>
      </form>
      {localError ? (
        <p className="progressError" role="alert">
          {localError}
        </p>
      ) : null}
      {profile && rowVersion !== undefined && allowedChange ? (
        <CommandForm
          label={changeStatus === "publish" ? "Publicar perfil Procurement" : "Crear sucesor del perfil Procurement"}
          spec={{}}
          busy={controls.busy}
          profile={null}
          submit={async (body) => {
            const row = await controls.command(`${path}/${changeStatus}`, body, rowVersion);
            if (row && text(row.id)) select(text(row.id));
            return row;
          }}
        />
      ) : null}
    </section>
  );
}

export default function ProcurementProfilesAdminView({ token }: { token: string }) {
  const [selected, select] = useState<string | null>(null);
  const controls = useProcurementCommands(token, procurementAdmin);
  const data = useProcurementRead(token, procurementAdmin, "", controls.revision);
  const profiles = rows(data.value);
  const defaults = isRow(data.value?.default_content) ? data.value.default_content : null;
  const profile = profiles.find((entry) => text(entry.id) === selected) ?? null;
  const can = (action: string) => !data.error && permission(data.value?.allowed_actions, action);
  const visibleEditor = defaults && (profile || (selected === "" && can("admin.configure")));
  return (
    <section
      className="progressFoundation procurementFoundation"
      aria-label="Procurement Profiles ADMIN"
      aria-busy={controls.busy || data.loading}
    >
      <CompactModuleHeader
        title="Procurement Profiles"
        eyebrow="ADMIN MODE · O2B PROCUREMENT"
        description="Catálogos, límites de recepción, reglas de sourcing y separación de funciones."
        metrics={[{ label: "Perfiles", value: profiles.length }]}
      />
      <ReadState {...data} reload={controls.reload} />
      {controls.error ? (
        <p className="progressError" role="alert">
          {controls.error}
        </p>
      ) : null}
      {controls.message ? (
        <p className="progressNotice" role="status">
          {controls.message}
        </p>
      ) : null}
      {data.value && !data.error ? (
        <section className="progressPanel">
          {can("admin.configure") ? (
            <button type="button" onClick={() => select("")}>
              Nuevo perfil Procurement
            </button>
          ) : null}
          <Records
            label="Perfiles Procurement"
            items={profiles}
            columns={[
              ["code", "Código"],
              ["name", "Nombre"],
              ["revision", "Revisión"],
              ["status", "Estado"],
            ]}
            select={(row) => select(text(row.id))}
          />
        </section>
      ) : null}
      {visibleEditor ? (
        <Editor
          key={profile ? `${text(profile.id)}-${text(profile.version)}` : "draft"}
          profile={profile}
          defaults={defaults}
          controls={{ ...controls, busy: controls.busy || data.loading }}
          can={can}
          select={select}
        />
      ) : null}
    </section>
  );
}
