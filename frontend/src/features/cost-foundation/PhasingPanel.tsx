import { useState, type FormEvent } from "react";
import { Evidence, Input, Records, Select } from "./Fields";
import { collection, text, type CostPanelProps } from "./types";

export default function PhasingPanel({ data, busy, reason, command, can }: CostPanelProps) {
  const [draft, setDraft] = useState({
    baseline_id: "",
    budget_line_id: "",
    method: "LINEAR",
    start_date: "",
    finish_date: "",
    schedule_version_id: "",
    source_external_id: "",
    period_id: "",
    curve_weights: "",
  });
  const [manual, setManual] = useState([{ date: "", amount: "" }]);
  const baseline = data.baselines.find((row) => String(row.id) === draft.baseline_id);
  const lines = data.budget_lines
    .filter((row) => row.budget_version_id === baseline?.budget_version_id)
    .map((row) => ({ ...row, code: text(row, "line_code"), name: text(row, "description") }));
  const schedule = data.schedule_versions.find((row) => String(row.id) === draft.schedule_version_id);
  const snapshot = schedule?.snapshot_json;
  const activities = collection(
    snapshot && typeof snapshot === "object" && !Array.isArray(snapshot) ? snapshot.activities : []
  );
  function set(key: keyof typeof draft, value: string) {
    setDraft({ ...draft, [key]: value });
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!baseline) return;
    await command(
      `/baselines/${baseline.id}/phase`,
      {
        budget_line_id: Number(draft.budget_line_id),
        method: draft.method,
        start_date: draft.start_date || null,
        finish_date: draft.finish_date || null,
        schedule_version_id: draft.schedule_version_id ? Number(draft.schedule_version_id) : null,
        source_external_id: draft.source_external_id,
        period_id: draft.period_id ? Number(draft.period_id) : null,
        manual_spread: draft.method === "MANUAL" ? manual : [],
        curve_weights:
          draft.method === "CURVE_BASED" ? draft.curve_weights.split(",").map((value) => value.trim()) : [],
        reason,
      },
      baseline.version
    );
  }
  return (
    <section className="costPanel">
      <h3>Cost Phasing</h3>
      <p>
        Schedule conserva la autoridad de fechas. La distribución registra fuente, revisión, período y método. Períodos
        CLOSED/PUBLISHED no se reescriben.
      </p>
      <Records
        label="Cost Phasing"
        rows={data.phasing}
        columns={[
          ["baseline_id", "Baseline"],
          ["budget_line_id", "Budget line"],
          ["method", "Método"],
          ["start_date", "Inicio"],
          ["finish_date", "Fin"],
          ["amount", "Importe"],
          ["currency", "Moneda"],
          ["period_id", "Período"],
          ["revision", "Revisión"],
        ]}
      />
      {can("phasing.edit") ? (
        <form className="costForm" onSubmit={(event) => void save(event).catch(() => undefined)}>
          <Select
            label="Phasing Cost Baseline"
            required
            rows={data.baselines.filter((row) => row.status === "CANDIDATE")}
            value={draft.baseline_id}
            onChange={(value) => set("baseline_id", value)}
          />
          <Select
            label="Phasing Budget Line"
            required
            rows={lines}
            value={draft.budget_line_id}
            onChange={(value) => set("budget_line_id", value)}
          />
          <Select
            label="Cost Phasing Method"
            required
            values={[
              "LINEAR",
              "FRONT_LOADED",
              "BACK_LOADED",
              "MILESTONE_BASED",
              "ACTIVITY_BASED",
              "MANUAL",
              "CURVE_BASED",
            ]}
            value={draft.method}
            onChange={(value) => set("method", value)}
          />
          <Select
            label="Phasing Schedule Version"
            required={draft.method === "ACTIVITY_BASED"}
            rows={data.schedule_versions}
            value={draft.schedule_version_id}
            onChange={(value) => set("schedule_version_id", value)}
          />
          <Select
            label="Phasing Activity"
            required={draft.method === "ACTIVITY_BASED"}
            values={activities.map((row) => text(row, "external_id"))}
            value={draft.source_external_id}
            onChange={(value) => set("source_external_id", value)}
          />
          <Select
            label="Phasing Project Controls Period"
            rows={data.periods.filter((row) => ["OPEN", "REVIEW"].includes(text(row, "status")))}
            value={draft.period_id}
            onChange={(value) => set("period_id", value)}
          />
          <Input
            label="Phasing Start Date"
            type="date"
            value={draft.start_date}
            onChange={(value) => set("start_date", value)}
            required={!["ACTIVITY_BASED", "MANUAL"].includes(draft.method)}
          />
          <Input
            label="Phasing Finish Date"
            type="date"
            value={draft.finish_date}
            onChange={(value) => set("finish_date", value)}
            required={!["ACTIVITY_BASED", "MANUAL"].includes(draft.method)}
          />
          {draft.method === "MANUAL" ? (
            <>
              {manual.map((row, index) => (
                <div className="costForm costWide" key={index}>
                  <Input
                    label={`Manual Phasing Date ${index + 1}`}
                    required
                    type="date"
                    value={row.date}
                    onChange={(date) =>
                      setManual(manual.map((item, position) => (position === index ? { ...item, date } : item)))
                    }
                  />
                  <Input
                    label={`Manual Phasing Amount ${index + 1}`}
                    required
                    type="number"
                    value={row.amount}
                    onChange={(amount) =>
                      setManual(manual.map((item, position) => (position === index ? { ...item, amount } : item)))
                    }
                  />
                </div>
              ))}
              <button type="button" onClick={() => setManual([...manual, { date: "", amount: "" }])}>
                Agregar fecha manual
              </button>
            </>
          ) : null}
          {draft.method === "CURVE_BASED" ? (
            <Input
              label="Phasing Curve Weights"
              required
              value={draft.curve_weights}
              onChange={(value) => set("curve_weights", value)}
            />
          ) : null}
          <button type="submit" disabled={busy || !baseline || reason.trim().length < 8}>
            Distribuir Cost Baseline
          </button>
        </form>
      ) : null}
      <Evidence label="Fuentes y distribuciones Cost Phasing" value={data.phasing} />
    </section>
  );
}
