import { useState } from "react";
import { engineeringQuery, items, labelOf, optionalId, recordId, text, versionOf, type EngineeringRow } from "./api";
import { Options, ReadState, Reason, Records, Select, SubmitForm } from "./controls";
import { useEngineeringData } from "./hooks";
import type { EngineeringScope } from "./types";

const mappingKinds = [
  "EWP",
  "CWP",
  "IWP",
  "CWA",
  "SCOPE",
  "PLAN",
  "WBS",
  "ACTIVITY",
  "MILESTONE",
  "CBS",
  "COST_CODE",
  "CONTROL_ACCOUNT",
];

function targetKey(row: EngineeringRow) {
  return [text(row.target_id ?? row.id), text(row.schedule_version_id), text(row.external_id)].join(":");
}

export function MappingsPanel({
  scope,
  parent,
  mode,
  editable,
}: {
  scope: EngineeringScope;
  parent: EngineeringRow;
  mode: "revisions" | "design-packages";
  editable: boolean;
}) {
  const path = `/${mode}/${recordId(parent)}/mappings`;
  const [kind, setKind] = useState(mode === "design-packages" ? "EWP" : "");
  const [target, setTarget] = useState("");
  const [remove, setRemove] = useState<EngineeringRow | null>(null);
  const [reason, setReason] = useState("");
  const mappings = useEngineeringData(scope.token, scope.base, path, scope.refreshKey);
  const targets = useEngineeringData(
    scope.token,
    scope.base,
    editable && kind ? engineeringQuery("/mapping-targets", { target_kind: kind }) : null,
    scope.refreshKey
  );
  const available = items(targets.value).map<EngineeringRow>((row) => ({ ...row, key: targetKey(row) }));
  const targetRow = available.find((row) => row.key === target);
  const version = versionOf(mappings.value);
  const canEdit = editable && scope.can("mapping.edit") && version !== undefined;
  const latest = items(mappings.value);
  const active = latest.filter(
    (row) => row.active !== false && text(row.action) !== "REMOVE" && text(row.status) !== "REMOVED"
  );
  const selectable = active.map((row) => ({
    ...row,
    selectionKey: recordId(row) || `${text(row.target_kind)}-${targetKey(row)}`,
  }));
  async function change() {
    if (!canEdit || (!remove && (!targetRow || !kind))) return;
    const source = remove ?? targetRow;
    if (!source) return;
    const targetKind = remove ? text(remove.target_kind) : kind;
    const schedule = ["WBS", "ACTIVITY", "MILESTONE"].includes(targetKind);
    const targetId = optionalId(text(source.target_id ?? source.id));
    const scheduleId = optionalId(text(source.schedule_version_id));
    const externalId = text(source.external_id);
    if (schedule ? !(scheduleId && externalId) : !targetId) return;
    const row = await scope.command(
      path,
      {
        action: remove ? "REMOVE" : "SET",
        target_kind: targetKind,
        ...(schedule ? { schedule_version_id: scheduleId, external_id: externalId } : { target_id: targetId }),
        reason: reason.trim(),
      },
      version
    );
    if (row) {
      setTarget("");
      setRemove(null);
      setReason("");
    }
  }
  return (
    <section className="progressPanel" aria-label="Enlaces de Ingeniería">
      <h3>Mapeos por identidad</h3>
      <p className="engineeringRoles">
        El enlace es de Ingeniería. No crea ni modifica objetos de Scope, AWP, Cost o Schedule.
      </p>
      <ReadState {...mappings} reload={scope.reload} />
      {mappings.value ? (
        <Records
          label="Mapeos Engineering"
          items={latest}
          columns={[
            ["target_kind", "Tipo"],
            ["target_id", "ID"],
            ["external_id", "Identidad importada"],
            ["schedule_version_id", "Schedule Version"],
            ["target_snapshot_json", "Destino"],
            ["status", "Estado"],
            ["mapping_health", "Vigencia"],
          ]}
        />
      ) : null}
      {canEdit ? (
        <SubmitForm onSubmit={change} disabled={scope.busy || mappings.loading}>
          {selectable.length ? (
            <Options
              label="Quitar enlace existente"
              value={remove ? recordId(remove) || `${text(remove.target_kind)}-${targetKey(remove)}` : ""}
              onChange={(key) => setRemove(selectable.find((row) => row.selectionKey === key) ?? null)}
              records={selectable}
              valueKey="selectionKey"
              render={(row) => `${text(row.target_kind)} · ${text(row.external_id ?? row.target_id)}`}
            />
          ) : null}
          {!remove ? (
            <>
              <Select
                label="Tipo de destino Engineering"
                value={kind}
                onChange={(value) => {
                  setKind(value);
                  setTarget("");
                }}
                values={mode === "design-packages" ? ["EWP"] : mappingKinds}
                required
              />
              <Options
                label="Destino Engineering"
                value={target}
                onChange={setTarget}
                records={available}
                valueKey="key"
                render={(row) => `${labelOf(row)} · ${text(row.target_id ?? row.external_id ?? row.id)}`}
                disabled={!kind || targets.loading}
                required
              />
            </>
          ) : null}
          <Reason label="Motivo del enlace" value={reason} onChange={setReason} />
          <button type="submit" disabled={!remove && !targetRow}>
            {remove ? "Retirar enlace Engineering" : "Agregar enlace Engineering"}
          </button>
        </SubmitForm>
      ) : null}
      {canEdit && kind ? <ReadState {...targets} reload={scope.reload} /> : null}
    </section>
  );
}
