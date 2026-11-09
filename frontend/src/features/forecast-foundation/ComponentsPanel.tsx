import { useState, type FormEvent } from "react";
import { Evidence, Input, Records, Select } from "./Fields";
import {
  forecastMethods,
  object,
  text,
  type ComponentFamily,
  type ForecastComponent,
  type ForecastEditorProps,
} from "./types";

const titles: Record<ComponentFamily, string> = {
  cost_items: "Cost Forecast Components",
  time_items: "Time Forecast Components",
  milestones: "Forecast Milestones",
  resource_items: "Resource Forecast Components",
};
const referenceFields = [
  ["amount_assumption_code", "Amount"],
  ["quantity_assumption_code", "Remaining quantity"],
  ["rate_assumption_code", "Rate"],
  ["productivity_assumption_code", "Forecast productivity"],
  ["duration_assumption_code", "Remaining duration"],
  ["trend_factor_assumption_code", "Trend factor"],
  ["date_assumption_code", "Forecast date"],
  ["crew_assumption_code", "Crew"],
  ["planned_productivity_assumption_code", "Planned productivity"],
  ["actual_productivity_assumption_code", "Actual productivity"],
] as const;
const blank = (family: ComponentFamily): ForecastComponent => ({
  code: "",
  name: "",
  method:
    family === "cost_items"
      ? "BOTTOM_UP"
      : family === "resource_items"
        ? "PRODUCTIVITY_BASED"
        : "ACTIVITY_REMAINING_DURATION",
  assumption_codes: [],
  activity_external_id: "",
  wbs_external_id: "",
  area: "",
  zone: "",
  system: "",
  discipline: "",
  currency: null,
  unit: "",
  inputs:
    family === "cost_items"
      ? { cost_bucket: "UNCOMMITTED" }
      : family === "resource_items"
        ? { resource_type: "LABOR", productivity_basis: "QUANTITY_PER_DAY" }
        : family === "milestones"
          ? { milestone_type: "KEY_PROJECT" }
          : {},
});

export default function ComponentsPanel(props: ForecastEditorProps & { family: ComponentFamily }) {
  const title = titles[props.family];
  const [entry, setEntry] = useState<ForecastComponent>(() => blank(props.family));
  const [index, setIndex] = useState<number | null>(null);
  const [commitmentIds, setCommitmentIds] = useState("");
  const [incurredActualIds, setIncurredActualIds] = useState("");
  const [error, setError] = useState("");
  const [phaseDate, setPhaseDate] = useState("");
  const [phaseAmount, setPhaseAmount] = useState("");
  const field = (key: keyof ForecastComponent, value: unknown) => setEntry((current) => ({ ...current, [key]: value }));
  const input = (key: string, value: unknown) =>
    setEntry((current) => ({ ...current, inputs: { ...current.inputs, [key]: value } }));
  const assumptions = props.draft.assumptions.map((value) => ({
    id: value.code,
    code: value.code,
    name: `${value.name} · ${value.value} ${value.unit}`,
  }));
  function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (props.draft[props.family].some((row, position) => position !== index && row.code === entry.code)) {
      setError("El código del componente ya existe en esta familia.");
      return;
    }
    const ids = commitmentIds.trim() ? commitmentIds.split(",").map((value) => Number(value.trim())) : [];
    const actualIds = incurredActualIds.trim() ? incurredActualIds.split(",").map((value) => Number(value.trim())) : [];
    if ([...ids, ...actualIds].some((value) => !Number.isInteger(value) || value <= 0)) {
      setError("Las referencias de compromiso deben ser identificadores positivos separados por comas.");
      return;
    }
    const inputs = { ...entry.inputs };
    if (ids.length) inputs.commitment_ids = ids;
    else delete inputs.commitment_ids;
    if (actualIds.length) inputs.incurred_actual_ids = actualIds;
    else delete inputs.incurred_actual_ids;
    const referenced = referenceFields.map(([key]) => text(inputs, key)).filter(Boolean);
    const component = { ...entry, inputs, assumption_codes: [...new Set(referenced)] };
    props.setDraft({
      ...props.draft,
      [props.family]:
        index === null
          ? [...props.draft[props.family], component]
          : props.draft[props.family].map((row, position) => (position === index ? component : row)),
    });
    setEntry(blank(props.family));
    setIndex(null);
    setCommitmentIds("");
    setIncurredActualIds("");
  }
  function addPhase() {
    if (!phaseDate || phaseAmount === "") return;
    const phasing = Array.isArray(entry.inputs.phasing) ? entry.inputs.phasing : [];
    input("phasing", [...phasing, { date: phaseDate, amount: phaseAmount }]);
    setPhaseDate("");
    setPhaseAmount("");
  }
  const selectRef = (key: keyof ForecastComponent, label: string, options: typeof props.data.scope_items) => (
    <Select
      key={key}
      label={`${title} ${label}`}
      value={text(entry, key)}
      onChange={(value) => field(key, value ? Number(value) : null)}
      options={options}
      disabled={!props.editable}
    />
  );
  return (
    <section className="progressPanel" aria-label={title}>
      <h3>{title}</h3>
      <p>
        El método, la cobertura y las hipótesis se declaran por componente. El backend calcula los resultados y valida
        unidades, monedas y linaje; la UI no mantiene fórmulas financieras.
      </p>
      <Records
        label={title}
        items={props.draft[props.family]}
        columns={[
          ["code", "Código"],
          ["name", "Nombre"],
          ["method", "Método"],
          ["unit", "Unidad"],
          ["currency", "Moneda"],
          ["assumption_codes", "Hipótesis"],
          ["activity_external_id", "Activity"],
        ]}
        select={(row) => {
          const position = props.draft[props.family].findIndex((value) => value.code === row.code);
          if (position >= 0) {
            const value = props.draft[props.family][position];
            setEntry(value);
            setIndex(position);
            setCommitmentIds(Array.isArray(value.inputs.commitment_ids) ? value.inputs.commitment_ids.join(",") : "");
            setIncurredActualIds(
              Array.isArray(value.inputs.incurred_actual_ids) ? value.inputs.incurred_actual_ids.join(",") : ""
            );
          }
        }}
      />
      {error ? (
        <p className="progressError" role="alert">
          {error}
        </p>
      ) : null}
      <form className="progressForm" onSubmit={save}>
        <Input
          label={`${title} Code`}
          value={entry.code}
          onChange={(value) => field("code", value)}
          required
          disabled={!props.editable}
        />
        <Input
          label={`${title} Name`}
          value={entry.name}
          onChange={(value) => field("name", value)}
          required
          disabled={!props.editable}
        />
        <Select
          label={`${title} Method`}
          value={entry.method}
          onChange={(value) => field("method", value)}
          values={props.data.methods ?? forecastMethods}
          required
          disabled={!props.editable}
        />
        <Input
          label={`${title} Unit`}
          value={entry.unit}
          onChange={(value) => field("unit", value)}
          disabled={!props.editable}
        />
        <Input
          label={`${title} Currency`}
          value={entry.currency ?? ""}
          onChange={(value) => field("currency", value || null)}
          disabled={!props.editable}
        />
        {selectRef("scope_item_id", "Scope", props.data.scope_items)}
        {selectRef("plan_item_id", "Plan", props.data.plan_items)}
        {selectRef("work_package_id", "Work Package", props.data.packages)}
        {selectRef("control_account_id", "Control Account", props.data.control_accounts)}
        {selectRef("cbs_id", "CBS", props.data.cbs ?? [])}
        {selectRef("cost_code_id", "Cost Code", props.data.cost_codes ?? [])}
        {selectRef("schedule_version_id", "Schedule Version", props.data.schedule_versions)}
        <Input
          label={`${title} Activity external ID`}
          value={entry.activity_external_id}
          onChange={(value) => field("activity_external_id", value)}
          disabled={!props.editable}
        />
        <Input
          label={`${title} WBS external ID`}
          value={entry.wbs_external_id}
          onChange={(value) => field("wbs_external_id", value)}
          disabled={!props.editable}
        />
        {referenceFields.map(([key, name]) => (
          <Select
            key={key}
            label={`${title} ${name} assumption`}
            value={text(entry.inputs, key)}
            onChange={(value) => input(key, value)}
            options={assumptions}
            disabled={!props.editable}
          />
        ))}
        {props.family === "cost_items" ? (
          <>
            <Select
              label={`${title} ETC bucket`}
              value={text(entry.inputs, "cost_bucket", "UNCOMMITTED")}
              onChange={(value) => input("cost_bucket", value)}
              values={["COMMITTED", "UNCOMMITTED", "ALLOWANCE"]}
              required
              disabled={!props.editable}
            />
            <Input
              label={`${title} Commitment IDs`}
              value={commitmentIds}
              onChange={setCommitmentIds}
              disabled={!props.editable}
            />
          </>
        ) : null}
        {props.family === "resource_items" ? (
          <>
            <Select
              label={`${title} Resource Type`}
              value={text(entry.inputs, "resource_type", "LABOR")}
              onChange={(value) => input("resource_type", value)}
              values={[
                "LABOR",
                "EQUIPMENT",
                "CREW",
                "ENGINEERING_HOURS",
                "CONSTRUCTION_HOURS",
                "PROJECT_CONTROLS_HOURS",
              ]}
              required
              disabled={!props.editable}
            />
            <Select
              label={`${title} Productivity basis`}
              value={text(entry.inputs, "productivity_basis", "QUANTITY_PER_DAY")}
              onChange={(value) => input("productivity_basis", value)}
              values={["QUANTITY_PER_DAY", "HOURS_PER_UNIT"]}
              required
              disabled={!props.editable}
            />
          </>
        ) : null}
        {props.family === "milestones" ? (
          <Select
            label={`${title} Milestone Type`}
            value={text(entry.inputs, "milestone_type", "KEY_PROJECT")}
            onChange={(value) => input("milestone_type", value)}
            values={["CONTRACTUAL", "KEY_PROJECT", "INTERFACE", "COMMISSIONING", "HANDOVER"]}
            required
            disabled={!props.editable}
          />
        ) : null}
        {props.family === "cost_items" ? (
          <>
            <Input
              label={`${title} Recognized incurred Actual IDs`}
              value={incurredActualIds}
              onChange={setIncurredActualIds}
              disabled={!props.editable}
            />
            <Select
              label={`${title} Prior approved Forecast`}
              value={text(entry.inputs, "prior_forecast_id")}
              onChange={(value) => input("prior_forecast_id", value ? Number(value) : null)}
              options={props.data.versions.filter((value) => value.status === "APPROVED")}
              disabled={!props.editable}
            />
          </>
        ) : null}
        <details className="progressWide">
          <summary>Dimensiones de agrupación y distribución Forecast</summary>
          <div className="progressForm">
            <Input
              label={`${title} Quantity phase`}
              value={text(entry.inputs, "phase")}
              onChange={(value) => input("phase", value)}
              disabled={!props.editable}
            />
            {(["area", "zone", "system", "discipline"] as const).map((key) => (
              <Input
                key={key}
                label={`${title} ${key}`}
                value={entry[key]}
                onChange={(value) => field(key, value)}
                disabled={!props.editable}
              />
            ))}
            {props.family === "cost_items" ? (
              <fieldset className="progressWide">
                <legend>Distribución explícita del costo Forecast</legend>
                <p>
                  Fechas e importes de la proyección, sin cambiar el phasing de la línea base Cost. El backend
                  reconcilia esta distribución con el ETC.
                </p>
                <div className="progressForm">
                  <Input
                    label={`${title} Phase date`}
                    type="date"
                    value={phaseDate}
                    onChange={setPhaseDate}
                    disabled={!props.editable}
                  />
                  <Input
                    label={`${title} Phase amount`}
                    type="number"
                    value={phaseAmount}
                    onChange={setPhaseAmount}
                    disabled={!props.editable}
                  />
                  <button
                    type="button"
                    disabled={!props.editable || !phaseDate || phaseAmount === ""}
                    onClick={addPhase}
                  >
                    Añadir fecha Forecast
                  </button>
                  <button type="button" disabled={!props.editable} onClick={() => input("phasing", [])}>
                    Limpiar distribución local
                  </button>
                </div>
                <Evidence title="Distribución Forecast declarada" value={entry.inputs.phasing ?? []} />
              </fieldset>
            ) : null}
          </div>
        </details>
        {props.editable ? (
          <button type="submit" disabled={props.busy}>
            {index === null ? "Añadir componente al borrador" : "Actualizar componente del borrador"}
          </button>
        ) : null}
        {props.editable && index !== null ? (
          <button
            type="button"
            disabled={props.busy}
            onClick={() => {
              props.setDraft({
                ...props.draft,
                [props.family]: props.draft[props.family].filter((_, position) => position !== index),
              });
              setEntry(blank(props.family));
              setIndex(null);
              setCommitmentIds("");
              setIncurredActualIds("");
            }}
          >
            Quitar componente del borrador
          </button>
        ) : null}
      </form>
      <Evidence title={`${title} referencias y valores declarados`} value={object(entry)} />
    </section>
  );
}
