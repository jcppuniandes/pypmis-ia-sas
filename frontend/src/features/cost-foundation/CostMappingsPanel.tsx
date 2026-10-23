import { useState, type FormEvent } from "react";
import { Input, Records, Select } from "./Fields";
import { collection, text, type CostPanelProps, type CostRow } from "./types";

export default function CostMappingsPanel({ data, busy, reason, command, can }: CostPanelProps) {
  const [selected, setSelected] = useState<CostRow | null>(null);
  const [draft, setDraft] = useState({
    source_kind: "SCOPE",
    source_id: "",
    schedule_version_id: "",
    source_external_id: "",
    cbs_id: "",
    cost_code_id: "",
    control_account_id: "",
    allocation_basis: "QUANTITY",
    quantity_basis: "APPROVED_SCOPE",
    quantity: "",
    unit: "",
    percentage: "",
    amount: "",
    currency: "",
    effective_revision: "1",
    source_reference: "",
    status: "ACTIVE",
  });
  const isSchedule = draft.source_kind === "WBS" || draft.source_kind === "ACTIVITY";
  const version = data.schedule_versions.find((row) => String(row.id) === draft.schedule_version_id);
  const snapshot = version?.snapshot_json;
  const sourceRows =
    draft.source_kind === "SCOPE" ? data.scope_items : draft.source_kind === "PLAN" ? data.plan_items : data.packages;
  const scheduleRows = collection(
    snapshot && typeof snapshot === "object" && !Array.isArray(snapshot)
      ? snapshot[draft.source_kind === "WBS" ? "wbs" : "activities"]
      : []
  );
  function set(key: keyof typeof draft, value: string) {
    setDraft({ ...draft, [key]: value });
  }
  function select(row: CostRow) {
    setSelected(row);
    setDraft(
      (current) =>
        Object.fromEntries(
          Object.keys(current).map((key) => [key, text(row, key, key === "status" ? "ACTIVE" : "")])
        ) as typeof current
    );
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    const payload = {
      ...draft,
      source_id: isSchedule ? null : Number(draft.source_id),
      schedule_version_id: isSchedule ? Number(draft.schedule_version_id) : null,
      source_external_id: isSchedule ? draft.source_external_id : "",
      cbs_id: draft.cbs_id ? Number(draft.cbs_id) : null,
      cost_code_id: draft.cost_code_id ? Number(draft.cost_code_id) : null,
      control_account_id: draft.control_account_id ? Number(draft.control_account_id) : null,
      quantity: draft.quantity || null,
      percentage: draft.percentage || null,
      amount: draft.amount || null,
      currency: draft.currency || null,
      reason,
    };
    if (selected) await command(`/mappings/${selected.id}/successor`, payload, Number(selected.version));
    else await command("/mappings", payload);
  }
  return (
    <section className="costPanel">
      <h3>Scope / Plan / Package / Schedule ↔ Cost</h3>
      <p>
        Asignaciones M:N con base, revisión y fuente. No se alteran las cantidades aprobadas ni las fechas de Schedule.
      </p>
      <Records
        label="Cost Mappings"
        rows={data.mappings}
        columns={[
          ["source_kind", "Origen"],
          ["source_id", "ID origen"],
          ["source_external_id", "WBS / Activity"],
          ["cbs_id", "CBS"],
          ["cost_code_id", "Cost Code"],
          ["control_account_id", "Control Account"],
          ["allocation_basis", "Base"],
          ["quantity", "Cantidad"],
          ["unit", "Unidad"],
          ["effective_revision", "Revisión"],
          ["status", "Estado"],
        ]}
        select={select}
      />
      {can("mapping.edit") ? (
        <form className="costForm" onSubmit={(event) => void save(event).catch(() => undefined)}>
          {selected ? (
            <>
              <p className="costWide">
                Sucesor del mapping #{String(selected.id)}; el histórico anterior permanece inmutable.
              </p>
              <button
                type="button"
                onClick={() => {
                  setSelected(null);
                  setDraft({ ...draft, status: "ACTIVE" });
                }}
              >
                Nuevo Cost Mapping
              </button>
            </>
          ) : null}
          <Select
            label="Cost Mapping Source Kind"
            required
            value={draft.source_kind}
            onChange={(value) => setDraft({ ...draft, source_kind: value, source_id: "", source_external_id: "" })}
            values={["SCOPE", "PLAN", "PACKAGE", "WBS", "ACTIVITY"]}
          />
          {isSchedule ? (
            <>
              <Select
                label="Cost Mapping Schedule Version"
                required
                value={draft.schedule_version_id}
                onChange={(value) => set("schedule_version_id", value)}
                rows={data.schedule_versions}
              />
              <Select
                label={`Cost Mapping ${draft.source_kind}`}
                required
                value={draft.source_external_id}
                onChange={(value) => set("source_external_id", value)}
                values={scheduleRows.map((row) => text(row, "external_id"))}
              />
            </>
          ) : (
            <Select
              label={`Cost Mapping ${draft.source_kind}`}
              required
              value={draft.source_id}
              onChange={(value) => set("source_id", value)}
              rows={sourceRows}
            />
          )}
          <Select
            label="Cost Mapping CBS"
            value={draft.cbs_id}
            onChange={(value) => set("cbs_id", value)}
            rows={data.cbs}
          />
          {selected ? (
            <Select
              label="Cost Mapping Status"
              required
              values={["ACTIVE", "REMOVED"]}
              value={draft.status}
              onChange={(value) => set("status", value)}
            />
          ) : null}
          <Select
            label="Cost Mapping Cost Code"
            value={draft.cost_code_id}
            onChange={(value) => set("cost_code_id", value)}
            rows={data.cost_codes}
          />
          <Select
            label="Cost Mapping Control Account"
            value={draft.control_account_id}
            onChange={(value) => set("control_account_id", value)}
            rows={data.control_accounts}
          />
          {(
            [
              "allocation_basis",
              "quantity_basis",
              "quantity",
              "unit",
              "percentage",
              "amount",
              "currency",
              "effective_revision",
              "source_reference",
            ] as const
          ).map((key) => (
            <Input
              key={key}
              label={`Cost Mapping ${key}`}
              value={draft[key]}
              onChange={(value) => set(key, value)}
              required={["allocation_basis", "quantity_basis", "effective_revision", "source_reference"].includes(key)}
              type={["quantity", "percentage", "amount"].includes(key) ? "number" : "text"}
            />
          ))}
          <button
            type="submit"
            disabled={
              busy || reason.trim().length < 8 || !(draft.cbs_id || draft.cost_code_id || draft.control_account_id)
            }
          >
            {selected ? "Guardar Cost Mapping sucesor" : "Guardar Cost Mapping"}
          </button>
        </form>
      ) : null}
    </section>
  );
}
