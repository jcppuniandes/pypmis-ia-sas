import { useState, type FormEvent } from "react";
import { Evidence, Facts, Input, Records, Select } from "./Fields";
import {
  display,
  effectiveStatus,
  object,
  percentage,
  physicalMethods,
  revision,
  rows,
  text,
  weightingBases,
  type ProgressPanelProps,
  type ProgressRow,
} from "./types";

const empty = {
  code: "",
  name: "",
  method: "QUANTITY_BASED",
  source_kind: "SCOPE",
  source_id: "",
  source_reference: "",
  measurement_date: "",
  numerator: "0",
  unit: "",
  scope_nature: "INSTALL",
  phase: "INSTALL",
  input_mode: "CUMULATIVE",
  denominator_basis: "AUTO",
  weight: "1",
  weighting_basis: "MANUAL_APPROVED_WEIGHT",
  rule_id: "",
  schedule_version_id: "",
  activity_external_id: "",
  control_account_id: "",
  wbs_external_id: "",
  area: "",
  system: "",
  discipline: "",
  evidence_kind: "FIELD_REPORT",
  evidence_reference: "",
  evidence_hash: "",
  correction_kind: "NONE",
};
type MeasurementForm = typeof empty;
export default function MeasurementsPanel(
  props: ProgressPanelProps & { progressType: "QUANTITY" | "PHYSICAL" | "MILESTONE" | "WEIGHTED" }
) {
  const { data, periodId, asOf, reason, busy, can, command, progressType } = props;
  const [form, setForm] = useState<MeasurementForm>({
    ...empty,
    method:
      progressType === "MILESTONE"
        ? "MILESTONE_BASED"
        : progressType === "WEIGHTED"
          ? "WEIGHTED_COMPONENTS"
          : "QUANTITY_BASED",
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [completed, setCompleted] = useState<string[]>([]);
  const [components, setComponents] = useState<Record<string, string>>({});
  const items = data.measurements.filter((row) => row.progress_type === progressType);
  const selected = data.measurements.find((row) => row.id === selectedId);
  const sourceOptions =
    form.source_kind === "SCOPE"
      ? data.scope_items.filter((row) => row.status === "APPROVED")
      : form.source_kind === "PLAN"
        ? data.plan_items.filter((row) => row.status === "PUBLISHED")
        : data.packages;
  const source = sourceOptions.find((row) => text(row, "id") === form.source_id);
  const rule = data.rules.find((row) => text(row, "id") === form.rule_id);
  const steps = rows(rule?.steps_json ?? rule?.steps);
  const usesRule = ["MILESTONE_BASED", "STEP_METHOD", "RULE_OF_CREDIT"].includes(form.method);
  const needsRule =
    usesRule ||
    form.denominator_basis === "APPROVED_RULE" ||
    ["LABOR_HOURS", "ENGINEERING_HOURS", "CONTRACT_VALUE"].includes(form.weighting_basis);
  const usesComponents = form.method === "WEIGHTED_COMPONENTS";
  const currentPeriod = data.periods.find((row) => text(row, "id") === periodId);
  const open = currentPeriod?.status === "OPEN";
  const editable = can("capture") && open && (!selected || selected.status === "DRAFT");
  const canSuccessor = can("capture") && open && selected?.status === "APPROVED";
  const ready = !busy && Boolean(periodId && asOf && reason.trim().length >= 8);
  const set = (key: keyof MeasurementForm, value: string) => setForm((current) => ({ ...current, [key]: value }));
  function choose(row: ProgressRow) {
    setSelectedId(Number(row.id));
    const kind = row.scope_item_id
      ? "SCOPE"
      : row.plan_item_id
        ? "PLAN"
        : row.work_package_id
          ? "PACKAGE"
          : row.method === "WEIGHTED_COMPONENTS"
            ? "PROJECT"
            : "PACKAGE";
    const input = { ...row, ...object(row.input_json) };
    const evidence = rows(row.evidence_json ?? row.evidence_refs ?? row.evidence_refs_json)[0] ?? {};
    const value = { ...empty };
    for (const key of Object.keys(empty) as (keyof MeasurementForm)[]) value[key] = text(input, key, value[key]);
    value.source_kind = kind;
    value.source_id = text(
      row,
      kind === "SCOPE" ? "scope_item_id" : kind === "PLAN" ? "plan_item_id" : "work_package_id"
    );
    value.evidence_kind = text(evidence, "kind", "FIELD_REPORT");
    value.evidence_reference = text(evidence, "reference");
    value.evidence_hash = text(evidence, "content_hash");
    setForm(value);
    setCompleted(Array.isArray(input.completed_steps) ? input.completed_steps.map(String) : []);
    setComponents(
      Object.fromEntries(
        rows(input.components ?? row.components_json).map((entry) => [
          text(entry, "measurement_id"),
          text(entry, "weight"),
        ])
      )
    );
  }
  function reset() {
    setSelectedId(null);
    setForm({
      ...empty,
      method:
        progressType === "MILESTONE"
          ? "MILESTONE_BASED"
          : progressType === "WEIGHTED"
            ? "WEIGHTED_COMPONENTS"
            : "QUANTITY_BASED",
    });
    setCompleted([]);
    setComponents({});
  }
  async function save(event: FormEvent, successor = false) {
    event.preventDefault();
    const evidence = [
      {
        kind: form.evidence_kind,
        reference: form.evidence_reference,
        ...(form.evidence_hash ? { content_hash: form.evidence_hash } : {}),
      },
    ];
    const payload = {
      code: form.code,
      name: form.name,
      progress_type: progressType,
      method: form.method,
      source_reference: form.source_reference,
      period_id: Number(periodId),
      measurement_date: form.measurement_date,
      as_of: asOf,
      numerator: form.numerator,
      unit: form.unit,
      scope_nature: form.scope_nature,
      phase: form.phase,
      input_mode: form.input_mode,
      denominator_basis: form.denominator_basis,
      weight: form.weight,
      weighting_basis: form.weighting_basis,
      evidence_refs: evidence,
      correction_kind: form.correction_kind,
      scope_item_id: form.source_kind === "SCOPE" ? Number(form.source_id) : null,
      plan_item_id: form.source_kind === "PLAN" ? Number(form.source_id) : null,
      work_package_id: form.source_kind === "PACKAGE" ? Number(form.source_id) : null,
      schedule_version_id: form.schedule_version_id ? Number(form.schedule_version_id) : null,
      activity_external_id: form.activity_external_id,
      control_account_id: form.control_account_id ? Number(form.control_account_id) : null,
      wbs_external_id: form.wbs_external_id,
      area: form.area,
      system: form.system,
      discipline: form.discipline,
      rule_id: form.rule_id ? Number(form.rule_id) : null,
      completed_steps: completed,
      components: Object.entries(components)
        .filter(([, weight]) => weight !== "")
        .map(([measurement_id, weight]) => ({ measurement_id: Number(measurement_id), weight })),
      reason,
    };
    const path = selected ? `/measurements/${selected.id}${successor ? "/successor" : ""}` : "/measurements";
    const result = await command(
      path,
      payload,
      selected ? revision(selected) : undefined,
      selected && !successor ? "PUT" : "POST"
    );
    setSelectedId(Number(result.id));
  }
  function transition(status: string) {
    if (selected)
      void command(`/measurements/${selected.id}/transition`, { status, reason }, revision(selected)).catch(
        () => undefined
      );
  }
  return (
    <section className="progressPanel" aria-label={`${progressType} measurement panel`}>
      <h3>
        {progressType === "QUANTITY"
          ? "Quantity Progress"
          : progressType === "PHYSICAL"
            ? "Physical Progress"
            : progressType === "MILESTONE"
              ? "Milestone Progress"
              : "Weighted Progress"}
      </h3>
      <p>
        {progressType === "QUANTITY"
          ? "La cantidad completada se contrasta con la base aprobada de Scope, Plan o paquete. El denominador y su linaje los resuelve el backend."
          : "Medición independiente del porcentaje P6, el costo, las facturas y los pagos. Solo el avance aprobado puede alimentar los resultados ganados."}
      </p>
      <Records
        label={`${progressType} measurements`}
        items={items}
        columns={[
          ["code", "Código"],
          ["method", "Método"],
          ["progress_value", "Acumulado %"],
          ["period_progress", "Avance del período %"],
          ["period_quantity", "Cantidad del período"],
          ["cumulative_quantity", "Cantidad acumulada"],
          ["unit", "Unidad"],
          ["status", "Estado"],
          ["revision", "Revisión"],
        ]}
        select={choose}
      />
      {selected ? (
        <>
          <Facts
            values={[
              ["Medición", selected.code],
              ["Estado efectivo", effectiveStatus(selected)],
              ["Vigencia de fuentes", selected.source_state],
              ["Variación", selected.variance ?? selected.variance_json],
              ["Avance acumulado", percentage(selected.progress_value)],
              ["Avance del período", percentage(selected.period_progress)],
              ["Cantidad del período", selected.period_quantity],
              ["Denominador aprobado", selected.denominator],
              ["Fecha de medición registrada", selected.measurement_date],
              ["As-of registrado", selected.as_of],
              ["Período registrado", selected.period_id],
              ["Preparador", selected.prepared_by ?? selected.created_by],
              ["Certificador", selected.certified_by],
              ["Aprobador", selected.approved_by],
            ]}
          />
          <div className="progressActions">
            {can("submit") && selected.status === "DRAFT" ? (
              <button disabled={!ready} onClick={() => transition("SUBMITTED")}>
                Enviar {progressType}
              </button>
            ) : null}
            {can("review") && selected.status === "SUBMITTED" ? (
              <button disabled={!ready} onClick={() => transition("UNDER_REVIEW")}>
                Revisar {progressType}
              </button>
            ) : null}
            {can(selected.method === "QUANTITY_BASED" ? "quantity.certify" : "milestone.certify") &&
            ["SUBMITTED", "UNDER_REVIEW"].includes(selected.status) ? (
              <button
                disabled={!ready || !form.evidence_reference}
                onClick={() =>
                  void command(
                    `/measurements/${selected.id}/certify`,
                    { reason, evidence_reference: form.evidence_reference },
                    revision(selected)
                  ).catch(() => undefined)
                }
              >
                Certificar {progressType}
              </button>
            ) : null}
            {can("approve") && selected.status === "UNDER_REVIEW" ? (
              <>
                <button disabled={!ready} onClick={() => transition("APPROVED")}>
                  Aprobar {progressType}
                </button>
                <button disabled={!ready} onClick={() => transition("REJECTED")}>
                  Rechazar {progressType}
                </button>
              </>
            ) : null}
          </div>
          <Evidence
            title="Fuentes y evidencia de la medición"
            value={{
              source_snapshot: selected.source_snapshot,
              source_hashes: selected.source_hashes,
              denominator: selected.denominator_snapshot,
              evidence_refs: selected.evidence_json ?? selected.evidence_refs ?? selected.evidence_refs_json,
              variance: selected.variance ?? selected.variance_json,
            }}
          />
        </>
      ) : null}
      {can("capture") ? (
        <button type="button" onClick={reset}>
          Nueva medición {progressType}
        </button>
      ) : null}
      {can("capture") ? (
        <form
          className="progressForm"
          aria-label={`${progressType} capture form`}
          onSubmit={(event) => void save(event, Boolean(canSuccessor)).catch(() => undefined)}
        >
          <h4 className="progressWide">
            {canSuccessor
              ? `Sucesor de ${text(selected, "code")}`
              : selected
                ? "Borrador seleccionado"
                : "Nueva medición gobernada"}
          </h4>
          {!open ? (
            <p className="progressWarning progressWide">
              El período seleccionado no está OPEN. No se permite capturar ni editar candidatos.
            </p>
          ) : null}
          <Input
            label={`${progressType} Code`}
            value={form.code}
            onChange={(value) => set("code", value)}
            required
            disabled={Boolean(selected) && !canSuccessor}
          />
          <Input label={`${progressType} Name`} value={form.name} onChange={(value) => set("name", value)} required />
          <Select
            label={`${progressType} Method`}
            value={form.method}
            onChange={(value) =>
              setForm((current) => ({
                ...current,
                method: value,
                ...(value !== "WEIGHTED_COMPONENTS" && current.source_kind === "PROJECT"
                  ? { source_kind: "SCOPE", source_id: "" }
                  : {}),
              }))
            }
            values={
              progressType === "QUANTITY"
                ? ["QUANTITY_BASED"]
                : progressType === "MILESTONE"
                  ? ["MILESTONE_BASED", "STEP_METHOD", "RULE_OF_CREDIT"]
                  : progressType === "WEIGHTED"
                    ? ["WEIGHTED_COMPONENTS"]
                    : (data.methods ?? physicalMethods)
            }
            required
          />
          <Select
            label={`${progressType} Source Kind`}
            value={form.source_kind}
            onChange={(value) => {
              set("source_kind", value);
              set("source_id", "");
            }}
            values={usesComponents ? ["SCOPE", "PLAN", "PACKAGE", "PROJECT"] : ["SCOPE", "PLAN", "PACKAGE"]}
            required
          />
          {form.source_kind === "PROJECT" ? (
            <p className="progressWide">
              Agregado del Project canónico. La cobertura procede de los componentes aprobados seleccionados, no de un
              Scope, Plan o paquete individual.
            </p>
          ) : (
            <Select
              label={`${progressType} ${form.source_kind}`}
              value={form.source_id}
              onChange={(value) => set("source_id", value)}
              options={sourceOptions}
              required
            />
          )}
          <Input
            label={`${progressType} Source reference`}
            value={form.source_reference}
            onChange={(value) => set("source_reference", value)}
            required
          />
          <Input
            label={`${progressType} Measurement date`}
            type="date"
            value={form.measurement_date}
            onChange={(value) => set("measurement_date", value)}
            required
          />
          <Input
            label={`${progressType} Numerator`}
            type="number"
            value={form.numerator}
            onChange={(value) => set("numerator", value)}
            required={!usesRule && !usesComponents}
          />
          <Input label={`${progressType} Unit`} value={form.unit} onChange={(value) => set("unit", value)} required />
          <Select
            label={`${progressType} Input mode`}
            value={form.input_mode}
            onChange={(value) => set("input_mode", value)}
            values={["CUMULATIVE", "PERIOD_DELTA"]}
            required
          />
          <Select
            label={`${progressType} Denominator basis`}
            value={form.denominator_basis}
            onChange={(value) => set("denominator_basis", value)}
            values={["AUTO", "SCOPE", "PLAN", "PACKAGE", "APPROVED_RULE"]}
            required
          />
          <Select
            label={`${progressType} Scope Nature`}
            value={form.scope_nature}
            onChange={(value) => set("scope_nature", value)}
            values={["INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"]}
            required
          />
          <Select
            label={`${progressType} Nature phase`}
            value={form.phase}
            onChange={(value) => set("phase", value)}
            values={["INSTALL", "REMOVE", "USE", "INTERVENTION", "RESTORATION", "EXECUTE"]}
            required
          />
          <Input
            label={`${progressType} Weight`}
            type="number"
            value={form.weight}
            onChange={(value) => set("weight", value)}
            required
          />
          <Select
            label={`${progressType} Weight basis`}
            value={form.weighting_basis}
            onChange={(value) => set("weighting_basis", value)}
            values={data.weighting_bases ?? weightingBases}
            required
          />
          {needsRule ? (
            <Select
              label={`${progressType} Published rule`}
              value={form.rule_id}
              onChange={(value) => {
                set("rule_id", value);
                setCompleted([]);
              }}
              options={data.rules.filter((row) => row.status === "PUBLISHED")}
              required
            />
          ) : null}
          {usesRule && steps.length ? (
            <fieldset className="progressWide">
              <legend>Pasos o hitos certificados</legend>
              {steps.map((step) => (
                <label className="progressCheck" key={text(step, "code")}>
                  <input
                    type="checkbox"
                    aria-label={`${progressType} Step ${text(step, "code")}`}
                    checked={completed.includes(text(step, "code"))}
                    onChange={(event) =>
                      setCompleted((current) =>
                        event.target.checked
                          ? [...current, text(step, "code")]
                          : current.filter((code) => code !== text(step, "code"))
                      )
                    }
                  />
                  {text(step, "name")} · {display(step.weight)} %
                </label>
              ))}
            </fieldset>
          ) : null}
          {usesComponents ? (
            <fieldset className="progressWide">
              <legend>Componentes aprobados y pesos explícitos</legend>
              {data.measurements
                .filter((row) => row.status === "APPROVED" && row.id !== selectedId)
                .map((row) => (
                  <Input
                    key={row.id}
                    label={`${progressType} Component ${row.id}`}
                    value={components[String(row.id)] ?? ""}
                    type="number"
                    onChange={(value) => setComponents((current) => ({ ...current, [row.id]: value }))}
                  />
                ))}
            </fieldset>
          ) : null}
          <Select
            label={`${progressType} Evidence kind`}
            value={form.evidence_kind}
            onChange={(value) => set("evidence_kind", value)}
            values={[
              "FIELD_REPORT",
              "QUANTITY_SHEET",
              "INSPECTION",
              "SURVEY",
              "PHOTO",
              "BIM_CONFIRMATION",
              "QA_RELEASE",
              "DOCUMENT",
              "MANUAL_CERTIFICATION",
            ]}
            required
          />
          <Input
            label={`${progressType} Evidence reference`}
            value={form.evidence_reference}
            onChange={(value) => set("evidence_reference", value)}
            required
          />
          <Input
            label={`${progressType} Evidence hash`}
            value={form.evidence_hash}
            onChange={(value) => set("evidence_hash", value)}
          />
          <Select
            label={`${progressType} Correction kind`}
            value={form.correction_kind}
            onChange={(value) => set("correction_kind", value)}
            values={["NONE", "REWORK", "REVERSAL", "QUANTITY_CORRECTION", "REJECTED_WORK", "DEMOLITION"]}
            required
          />
          <details className="progressWide">
            <summary>Dimensiones adicionales de control</summary>
            <div className="progressForm">
              <Select
                label={`${progressType} Schedule Version`}
                value={form.schedule_version_id}
                onChange={(value) => set("schedule_version_id", value)}
                options={data.schedule_versions}
              />
              <Input
                label={`${progressType} Activity external ID`}
                value={form.activity_external_id}
                onChange={(value) => set("activity_external_id", value)}
              />
              <Select
                label={`${progressType} Control Account`}
                value={form.control_account_id}
                onChange={(value) => set("control_account_id", value)}
                options={data.control_accounts}
              />
              {(["wbs_external_id", "area", "system", "discipline"] as const).map((key) => (
                <Input
                  key={key}
                  label={`${progressType} ${key}`}
                  value={form[key]}
                  onChange={(value) => set(key, value)}
                />
              ))}
            </div>
          </details>
          <p className="progressWide">
            Fuente seleccionada:{" "}
            {source
              ? display({
                  id: source.id,
                  nature: source.scope_nature ?? source.nature,
                  quantity: source.quantity,
                  unit: source.unit,
                  revision: source.revision,
                })
              : "Seleccione una fuente gobernada"}
            . Fecha as-of: {asOf || "sin seleccionar"}.
          </p>
          <button type="submit" disabled={!ready || !(editable || canSuccessor)}>
            {canSuccessor
              ? `Crear sucesor ${progressType}`
              : selected
                ? `Guardar ${progressType} DRAFT`
                : `Crear ${progressType} DRAFT`}
          </button>
        </form>
      ) : null}
      {selected ? <Evidence title="Snapshot técnico íntegro" value={object(selected)} /> : null}
    </section>
  );
}
