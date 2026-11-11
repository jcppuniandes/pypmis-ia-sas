import { useState } from "react";
import { engineeringQuery, items, labelOf, optionalId, recordId, text, versionOf, type EngineeringRow } from "./api";
import { Facts, Input, Notes, Options, ReadState, Reason, Records, Select, SubmitForm } from "./controls";
import { useEngineeringData } from "./hooks";
import { codeOptions, profileContent } from "./profile";
import type { EngineeringPanel } from "./types";

function RegisterEditor({
  row,
  scope,
  packages,
  onSaved,
}: {
  row: EngineeringRow | null;
  scope: EngineeringPanel;
  packages: EngineeringRow[];
  onSaved: (id: string) => void;
}) {
  const profile = profileContent(scope.config);
  const [draft, setDraft] = useState(() => ({
    code: text(row?.code),
    title: text(row?.title),
    discipline: text(row?.discipline),
    deliverable_type: text(row?.deliverable_type),
    design_package_id: text(row?.design_package_id),
    responsible_party: text(row?.responsible_party),
    description: text(row?.description),
    area: text(row?.area),
    planned_issue_date: text(row?.planned_issue_date),
    current_forecast_date: text(row?.current_forecast_date),
    source_reference: text(row?.source_reference),
    reason: "",
  }));
  const set = (key: keyof typeof draft) => (value: string) => setDraft((current) => ({ ...current, [key]: value }));
  const version = versionOf(row);
  const editable = row ? scope.can("deliverable.edit") && version !== undefined : scope.can("deliverable.create");
  const types = codeOptions(profile.deliverable_types).map((item) => item.code);
  const disciplines = codeOptions(profile.disciplines).map((item) => item.code);
  const ready = Boolean(types.length && disciplines.length);
  async function save() {
    if (!editable || !ready) return;
    const { code, reason, ...rest } = draft;
    const payload = {
      ...rest,
      title: rest.title.trim(),
      responsible_party: rest.responsible_party.trim(),
      design_package_id: optionalId(rest.design_package_id),
      planned_issue_date: rest.planned_issue_date || null,
      current_forecast_date: rest.current_forecast_date || null,
      area: rest.area.trim(),
      description: rest.description.trim(),
      source_reference: rest.source_reference.trim(),
      code: code.trim(),
      reason: reason.trim(),
    };
    const saved = await scope.command(
      row ? `/deliverables/${recordId(row)}` : "/deliverables",
      payload,
      version,
      row ? "PUT" : "POST"
    );
    if (saved) {
      onSaved(recordId(saved));
      set("reason")("");
    }
  }
  return (
    <section className="progressPanel" aria-label={row ? "Editar entregable" : "Nuevo entregable"}>
      <h3>{row ? `Entregable ${labelOf(row)}` : "Nuevo entregable técnico"}</h3>
      {row ? (
        <Facts
          values={[
            ["Estado", row.status],
            ["Aprobación", row.approval_status],
            ["IFC", row.ifc_release_status],
            ["Emisión real", row.actual_issue_date],
            ["Versión", row.version],
          ]}
        />
      ) : null}
      {!ready ? (
        <p className="progressWarning">
          Se requiere un perfil publicado con tipos y disciplinas para registrar entregables.
        </p>
      ) : null}
      <SubmitForm onSubmit={save} disabled={!editable || !ready || scope.busy}>
        <Input
          label="Código de entregable"
          value={draft.code}
          onChange={set("code")}
          required
          disabled={Boolean(row)}
        />
        <Input label="Título de entregable" value={draft.title} onChange={set("title")} required />
        <Select
          label="Tipo de entregable"
          value={draft.deliverable_type}
          onChange={set("deliverable_type")}
          values={types}
          required
          disabled={Boolean(row?.current_revision_id)}
        />
        <Select
          label="Disciplina"
          value={draft.discipline}
          onChange={set("discipline")}
          values={disciplines}
          required
          disabled={Boolean(row?.current_revision_id)}
        />
        <Input
          label="Responsable técnico"
          value={draft.responsible_party}
          onChange={set("responsible_party")}
          required
        />
        <Options
          label="Grupo de diseño"
          value={draft.design_package_id}
          onChange={set("design_package_id")}
          records={packages}
          render={labelOf}
        />
        <Input label="Área de Ingeniería" value={draft.area} onChange={set("area")} />
        <Input
          label="Fecha planificada"
          value={draft.planned_issue_date}
          onChange={set("planned_issue_date")}
          type="date"
        />
        <Input
          label="Fecha pronosticada"
          value={draft.current_forecast_date}
          onChange={set("current_forecast_date")}
          type="date"
        />
        <Input label="Referencia de origen" value={draft.source_reference} onChange={set("source_reference")} />
        <Notes label="Descripción técnica" value={draft.description} onChange={set("description")} />
        {editable ? (
          <>
            <Reason value={draft.reason} onChange={set("reason")} />
            <button type="submit">{row ? "Guardar entregable" : "Crear entregable"}</button>
          </>
        ) : null}
      </SubmitForm>
    </section>
  );
}

export default function RegisterPanel(scope: EngineeringPanel) {
  const [cursor, setCursor] = useState("");
  const [filter, setFilter] = useState("");
  const [editor, setEditor] = useState<"new" | "edit" | null>(null);
  const register = useEngineeringData(
    scope.token,
    scope.base,
    engineeringQuery("/deliverables", { after_id: cursor, limit: 50 }),
    scope.refreshKey
  );
  const groups = useEngineeringData(scope.token, scope.base, editor ? "/design-packages" : null, scope.refreshKey);
  const normalized = filter.trim().toLowerCase();
  const visible = items(register.value).filter((row) =>
    [row.code, row.title, row.discipline, row.deliverable_type, row.status].some((value) =>
      text(value).toLowerCase().includes(normalized)
    )
  );
  return (
    <>
      <section className="progressPanel" aria-label="Deliverable Register">
        <h3>Deliverable Register</h3>
        <div className="progressToolbar">
          <Input label="Buscar en esta página" value={filter} onChange={setFilter} />
          {scope.can("deliverable.create") ? (
            <button type="button" onClick={() => setEditor("new")}>
              Nuevo entregable
            </button>
          ) : null}
          {scope.deliverable && scope.can("deliverable.edit") ? (
            <button type="button" onClick={() => setEditor("edit")}>
              Editar entregable seleccionado
            </button>
          ) : null}
        </div>
        <ReadState {...register} reload={scope.reload} />
        {!register.error && !register.loading ? (
          <Records
            label="Entregables"
            items={visible}
            columns={[
              ["code", "Código"],
              ["title", "Entregable"],
              ["discipline", "Disciplina"],
              ["deliverable_type", "Tipo"],
              ["status", "Estado"],
              ["planned_issue_date", "Plan"],
              ["current_forecast_date", "Pronóstico"],
              ["ifc_release_status", "IFC"],
            ]}
            select={(row) => {
              scope.setDeliverableId(recordId(row));
              setEditor(null);
            }}
          />
        ) : null}
        {cursor || text(register.value?.next_cursor) ? (
          <div className="progressActions">
            {cursor ? (
              <button type="button" onClick={() => setCursor("")}>
                Primera página
              </button>
            ) : null}
            {text(register.value?.next_cursor) ? (
              <button type="button" onClick={() => setCursor(text(register.value?.next_cursor))}>
                Siguiente página
              </button>
            ) : null}
          </div>
        ) : null}
      </section>
      {editor && (editor === "new" || scope.deliverable) ? (
        <RegisterEditor
          key={editor === "new" ? "new" : `edit-${recordId(scope.deliverable)}`}
          row={editor === "new" ? null : scope.deliverable}
          scope={scope}
          packages={items(groups.value)}
          onSaved={(id) => {
            if (id) scope.setDeliverableId(id);
            setEditor(null);
          }}
        />
      ) : null}
    </>
  );
}
