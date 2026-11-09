import { useState, type FormEvent } from "react";
import { Evidence, Field, Input, Records, Select } from "./Fields";
import { object, rows, type ForecastAssumption, type ForecastEditorProps } from "./types";

const blank = (): ForecastAssumption => ({
  code: "",
  name: "",
  kind: "AMOUNT",
  value: "",
  unit: "",
  currency: null,
  source_reference: "",
  owner_id: 0,
  effective_date: "",
  confidence: "MEDIUM",
  status: "CONFIRMED",
  evidence_ref: "",
  rationale: "",
});

export default function AssumptionsPanel(props: ForecastEditorProps) {
  const [entry, setEntry] = useState<ForecastAssumption>(blank);
  const [index, setIndex] = useState<number | null>(null);
  const [error, setError] = useState("");
  const editable = props.editable && props.can("assumption.edit");
  const field = (key: keyof ForecastAssumption, value: unknown) =>
    setEntry((current) => ({ ...current, [key]: value }));
  function add(event: FormEvent) {
    event.preventDefault();
    if (!entry.owner_id || entry.owner_id <= 0) {
      setError("Indique un responsable válido de la hipótesis.");
      return;
    }
    const duplicate = props.draft.assumptions.some((row, position) => position !== index && row.code === entry.code);
    if (duplicate) {
      setError("El código de hipótesis ya existe en esta versión.");
      return;
    }
    props.setDraft({
      ...props.draft,
      assumptions:
        index === null
          ? [...props.draft.assumptions, entry]
          : props.draft.assumptions.map((row, position) => (position === index ? entry : row)),
    });
    setEntry(blank());
    setIndex(null);
    setError("");
  }
  return (
    <section className="progressPanel" aria-label="Forecast Assumptions">
      <h3>Assumptions</h3>
      <p>
        Hipótesis explícitas con fuente, responsable, fecha efectiva, unidad y evidencia. La confianza es una valoración
        gobernada, no un intervalo estadístico.
      </p>
      <Records
        label="Forecast Assumptions"
        items={props.draft.assumptions}
        columns={[
          ["code", "Código"],
          ["name", "Hipótesis"],
          ["kind", "Tipo"],
          ["value", "Valor"],
          ["unit", "Unidad"],
          ["currency", "Moneda"],
          ["owner_id", "Responsable"],
          ["effective_date", "Efectiva"],
          ["status", "Estado"],
        ]}
        select={(row) => {
          const position = props.draft.assumptions.findIndex((value) => value.code === row.code);
          if (position >= 0) {
            setEntry(props.draft.assumptions[position]);
            setIndex(position);
          }
        }}
      />
      {error ? (
        <p className="progressError" role="alert">
          {error}
        </p>
      ) : null}
      <form className="progressForm" onSubmit={add}>
        <Input
          label="Assumption Code"
          value={entry.code}
          onChange={(v) => field("code", v)}
          required
          disabled={!editable}
        />
        <Input
          label="Assumption Name"
          value={entry.name}
          onChange={(v) => field("name", v)}
          required
          disabled={!editable}
        />
        <Input
          label="Assumption Kind"
          value={entry.kind}
          onChange={(v) => field("kind", v)}
          required
          disabled={!editable}
        />
        <Input
          label="Assumption Value"
          value={entry.value}
          onChange={(v) => field("value", v)}
          required
          disabled={!editable}
        />
        <Input
          label="Assumption Unit"
          value={entry.unit}
          onChange={(v) => field("unit", v)}
          required
          disabled={!editable}
        />
        <Input
          label="Assumption Currency"
          value={entry.currency ?? ""}
          onChange={(v) => field("currency", v || null)}
          disabled={!editable}
        />
        <Input
          label="Assumption Source reference"
          value={entry.source_reference}
          onChange={(v) => field("source_reference", v)}
          required
          disabled={!editable}
        />
        <Field label="Assumption Owner ID">
          <input
            aria-label="Assumption Owner ID"
            type="number"
            min="1"
            required
            value={entry.owner_id || ""}
            onChange={(event) => field("owner_id", Number(event.target.value))}
            disabled={!editable}
          />
        </Field>
        <Input
          label="Assumption Effective date"
          type="date"
          value={entry.effective_date}
          onChange={(v) => field("effective_date", v)}
          required
          disabled={!editable}
        />
        <Select
          label="Assumption Confidence"
          value={entry.confidence}
          onChange={(v) => field("confidence", v)}
          values={["LOW", "MEDIUM", "HIGH"]}
          required
          disabled={!editable}
        />
        <Select
          label="Assumption Status"
          value={entry.status}
          onChange={(v) => field("status", v)}
          values={["DRAFT", "CONFIRMED"]}
          required
          disabled={!editable}
        />
        <Input
          label="Assumption Evidence reference"
          value={entry.evidence_ref}
          onChange={(v) => field("evidence_ref", v)}
          required
          disabled={!editable}
        />
        <Input
          label="Assumption Rationale"
          value={entry.rationale}
          onChange={(v) => field("rationale", v)}
          required
          disabled={!editable}
        />
        {editable ? (
          <button type="submit" disabled={props.busy}>
            {index === null ? "Añadir hipótesis al borrador" : "Actualizar hipótesis del borrador"}
          </button>
        ) : null}
        {editable && index !== null ? (
          <button
            type="button"
            disabled={props.busy}
            onClick={() => {
              props.setDraft({
                ...props.draft,
                assumptions: props.draft.assumptions.filter((_, position) => position !== index),
              });
              setEntry(blank());
              setIndex(null);
            }}
          >
            Quitar hipótesis del borrador
          </button>
        ) : null}
      </form>
      <p>
        Los cambios locales se persisten únicamente al guardar la versión Forecast. Las referencias usadas por un
        componente se validan en backend.
      </p>
      <Evidence
        title="Hipótesis y referencias congeladas de la versión"
        value={rows(object(props.selected).assumptions)}
      />
    </section>
  );
}
