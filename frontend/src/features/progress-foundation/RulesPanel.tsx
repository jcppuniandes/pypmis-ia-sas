import { useState, type FormEvent } from "react";
import { Evidence, Input, Records, Select } from "./Fields";
import { object, revision, rows, text, weightingBases, type ProgressPanelProps, type ProgressRow } from "./types";

type Step = { code: string; name: string; weight: string };
const installation: Step[] = [
  { code: "SET", name: "Set in position", weight: "30" },
  { code: "ALIGNED", name: "Aligned", weight: "20" },
  { code: "CONNECTED", name: "Connected", weight: "30" },
  { code: "TESTED", name: "Tested", weight: "20" },
];
export default function RulesPanel({ data, busy, reason, can, command }: ProgressPanelProps) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [method, setMethod] = useState("RULE_OF_CREDIT");
  const [steps, setSteps] = useState<Step[]>(installation);
  const [natures, setNatures] = useState(["INSTALL"]);
  const [packageTypes, setPackageTypes] = useState(["IWP"]);
  const [denominator, setDenominator] = useState("");
  const [unit, setUnit] = useState("");
  const [ordered, setOrdered] = useState(true);
  const [basisKind, setBasisKind] = useState("SCOPE");
  const [basisId, setBasisId] = useState("");
  const [basisReference, setBasisReference] = useState("");
  const [basisWeight, setBasisWeight] = useState("");
  const [basisWeighting, setBasisWeighting] = useState("LABOR_HOURS");
  const basisField =
    basisKind === "SCOPE" ? "scope_item_id" : basisKind === "PLAN" ? "plan_item_id" : "work_package_id";
  const basisOptions =
    basisKind === "SCOPE" ? data.scope_items : basisKind === "PLAN" ? data.plan_items : data.packages;
  const basis = () =>
    denominator || basisWeight
      ? {
          ...(denominator ? { denominator, unit } : {}),
          ...(basisWeight ? { weight: basisWeight, weighting_basis: basisWeighting } : {}),
          [basisField]: Number(basisId),
          source_reference: basisReference,
        }
      : {};
  const selected = data.rules.find((row) => row.id === selectedId);
  const editable = can("rule.manage") && (!selected || selected.status === "DRAFT");
  const ready = !busy && reason.trim().length >= 8;
  function choose(row: ProgressRow) {
    setSelectedId(Number(row.id));
    setCode(text(row, "code"));
    setName(text(row, "name"));
    setMethod(text(row, "method"));
    setSteps(
      rows(row.steps_json ?? row.steps).map((step) => ({
        code: text(step, "code"),
        name: text(step, "name"),
        weight: text(step, "weight"),
      }))
    );
    setNatures(Array.isArray(row.scope_natures) ? row.scope_natures.map(String) : ["INSTALL"]);
    setPackageTypes(Array.isArray(row.package_types) ? row.package_types.map(String) : ["IWP"]);
    setOrdered(row.ordered !== false);
    const source = object(row.measurement_basis);
    setDenominator(text(source, "denominator"));
    setUnit(text(source, "unit"));
    const kind = source.scope_item_id ? "SCOPE" : source.plan_item_id ? "PLAN" : "PACKAGE";
    setBasisKind(kind);
    setBasisId(text(source, kind === "SCOPE" ? "scope_item_id" : kind === "PLAN" ? "plan_item_id" : "work_package_id"));
    setBasisReference(text(source, "source_reference"));
    setBasisWeight(text(source, "weight"));
    setBasisWeighting(text(source, "weighting_basis", "LABOR_HOURS"));
  }
  function preset(value: string) {
    if (value === "INSTALLATION") setSteps(installation);
    else {
      const weights = value.split("/");
      setSteps(weights.map((weight, index) => ({ code: `STEP-${index + 1}`, name: `Hito ${index + 1}`, weight })));
    }
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    const payload = {
      code,
      name,
      method,
      steps,
      scope_natures: natures,
      package_types: packageTypes,
      ordered,
      measurement_basis: basis(),
      reason,
    };
    const result = await command(
      selected ? `/rules/${selected.id}` : "/rules",
      payload,
      selected ? revision(selected) : undefined,
      selected ? "PUT" : "POST"
    );
    setSelectedId(Number(result.id));
  }
  return (
    <section className="progressPanel" aria-label="Governed progress rules">
      <h3>Milestones / Rules of Credit</h3>
      <p>
        Plantillas versionadas. Los hitos de Progress pueden referenciar Schedule, pero no cambian sus fechas ni
        certifican automáticamente el avance.
      </p>
      <Records
        label="Progress Rules"
        items={data.rules}
        columns={[
          ["code", "Código"],
          ["name", "Nombre"],
          ["method", "Método"],
          ["status", "Estado"],
          ["revision", "Revisión"],
          ["published_by", "Publicador"],
        ]}
        select={choose}
      />
      {can("rule.manage") ? (
        <button
          type="button"
          onClick={() => {
            setSelectedId(null);
            setCode("");
            setName("");
            setSteps(installation);
            setDenominator("");
            setUnit("");
            setBasisId("");
            setBasisReference("");
            setBasisWeight("");
          }}
        >
          Nueva regla de crédito
        </button>
      ) : null}
      {can("rule.manage") || selected ? (
        <form className="progressForm" onSubmit={(event) => void save(event).catch(() => undefined)}>
          <Input label="Rule Code" value={code} onChange={setCode} required disabled={Boolean(selected) || !editable} />
          <Input label="Rule Name" value={name} onChange={setName} required disabled={!editable} />
          <Select
            label="Rule Method"
            value={method}
            onChange={setMethod}
            values={["RULE_OF_CREDIT", "STEP_METHOD", "MILESTONE_BASED"]}
            required
            disabled={!editable}
          />
          {editable ? (
            <Select
              label="Rule Preset"
              value=""
              onChange={preset}
              values={["INSTALLATION", "100", "50/50", "10/20/30/40"]}
            />
          ) : null}
          <div className="progressWide">
            {steps.map((step, index) => (
              <div className="progressStepRow" key={index}>
                <Input
                  label={`Rule Step Code ${index + 1}`}
                  value={step.code}
                  onChange={(value) =>
                    setSteps((current) => current.map((row, i) => (i === index ? { ...row, code: value } : row)))
                  }
                  required
                  disabled={!editable}
                />
                <Input
                  label={`Rule Step Name ${index + 1}`}
                  value={step.name}
                  onChange={(value) =>
                    setSteps((current) => current.map((row, i) => (i === index ? { ...row, name: value } : row)))
                  }
                  required
                  disabled={!editable}
                />
                <Input
                  label={`Rule Step Weight ${index + 1}`}
                  value={step.weight}
                  onChange={(value) =>
                    setSteps((current) => current.map((row, i) => (i === index ? { ...row, weight: value } : row)))
                  }
                  type="number"
                  required
                  disabled={!editable}
                />
                {editable ? (
                  <button
                    type="button"
                    disabled={steps.length <= 1}
                    onClick={() => setSteps((current) => current.filter((_, i) => i !== index))}
                  >
                    Quitar paso {index + 1}
                  </button>
                ) : null}
              </div>
            ))}
          </div>
          {editable ? (
            <button
              type="button"
              onClick={() => setSteps((current) => [...current, { code: "", name: "", weight: "0" }])}
            >
              Añadir paso
            </button>
          ) : null}
          <fieldset className="progressWide" disabled={!editable}>
            <legend>Scope Nature aplicable</legend>
            {["INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"].map((value) => (
              <label className="progressCheck" key={value}>
                <input
                  aria-label={`Rule Nature ${value}`}
                  type="checkbox"
                  checked={natures.includes(value)}
                  onChange={(event) =>
                    setNatures((current) =>
                      event.target.checked ? [...current, value] : current.filter((item) => item !== value)
                    )
                  }
                />
                {value}
              </label>
            ))}
          </fieldset>
          <fieldset className="progressWide" disabled={!editable}>
            <legend>Tipos de paquete aplicables</legend>
            {["EWP", "PWP", "CWP", "IWP", "TWP", "SUPPORT", "LOGISTICS", "TEMPORARY_WORKS"].map((value) => (
              <label className="progressCheck" key={value}>
                <input
                  aria-label={`Rule Package ${value}`}
                  type="checkbox"
                  checked={packageTypes.includes(value)}
                  onChange={(event) =>
                    setPackageTypes((current) =>
                      event.target.checked ? [...current, value] : current.filter((item) => item !== value)
                    )
                  }
                />
                {value}
              </label>
            ))}
          </fieldset>
          <Input
            label="Rule Approved denominator"
            type="number"
            value={denominator}
            onChange={setDenominator}
            disabled={!editable}
          />
          <Input label="Rule Basis unit" value={unit} onChange={setUnit} disabled={!editable} />
          <Select
            label="Rule Basis source kind"
            value={basisKind}
            onChange={(value) => {
              setBasisKind(value);
              setBasisId("");
            }}
            values={["SCOPE", "PLAN", "PACKAGE"]}
            disabled={!editable}
          />
          <Select
            label="Rule Basis source"
            value={basisId}
            onChange={setBasisId}
            options={basisOptions}
            disabled={!editable}
            required={Boolean(denominator || basisWeight)}
          />
          <Input
            label="Rule Basis source reference"
            value={basisReference}
            onChange={setBasisReference}
            required={Boolean(denominator || basisWeight)}
            disabled={!editable}
          />
          <Input
            label="Rule Basis approved weight"
            value={basisWeight}
            onChange={setBasisWeight}
            type="number"
            disabled={!editable}
          />
          <Select
            label="Rule Basis weighting method"
            value={basisWeighting}
            onChange={setBasisWeighting}
            values={weightingBases}
            disabled={!editable}
          />
          <label className="progressCheck progressWide">
            <input
              type="checkbox"
              aria-label="Rule Ordered steps"
              checked={ordered}
              onChange={(event) => setOrdered(event.target.checked)}
              disabled={!editable}
            />
            Exigir orden de pasos
          </label>
          {editable ? (
            <button type="submit" disabled={!ready}>
              {selected ? "Guardar regla DRAFT" : "Crear regla DRAFT"}
            </button>
          ) : null}
        </form>
      ) : null}
      {selected ? (
        <>
          <div className="progressActions">
            {can("rule.publish") && selected.status === "DRAFT" ? (
              <button
                disabled={!ready}
                onClick={() =>
                  void command(`/rules/${selected.id}/publish`, { reason }, revision(selected)).catch(() => undefined)
                }
              >
                Publicar regla
              </button>
            ) : null}
            {can("rule.manage") && selected.status === "PUBLISHED" ? (
              <button
                disabled={!ready}
                onClick={() =>
                  void command(
                    `/rules/${selected.id}/successor`,
                    {
                      code,
                      name,
                      method,
                      steps,
                      scope_natures: natures,
                      package_types: packageTypes,
                      ordered,
                      measurement_basis: basis(),
                      reason,
                    },
                    revision(selected)
                  )
                    .then((result) => setSelectedId(Number(result.id)))
                    .catch(() => undefined)
                }
              >
                Crear sucesor de regla
              </button>
            ) : null}
          </div>
          <p className="progressWarning">
            Publicación independiente del autor. Una regla publicada no se edita en sitio; la corrección crea otra
            revisión.
          </p>
          <Evidence title="Linaje y snapshot de la regla" value={selected} />
        </>
      ) : null}
    </section>
  );
}
