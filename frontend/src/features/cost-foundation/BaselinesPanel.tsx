import { useState, type FormEvent } from "react";
import { Evidence, Input, Records, Select } from "./Fields";
import { text, type CostPanelProps, type CostRow } from "./types";

export default function BaselinesPanel({ data, busy, reason, command, can }: CostPanelProps) {
  const [draft, setDraft] = useState({ code: "", budget_version_id: "", previous_baseline_id: "" });
  const [selectedId, setSelectedId] = useState("");
  const selected = data.baselines.find((row) => String(row.id) === selectedId);
  async function save(event: FormEvent) {
    event.preventDefault();
    const result = await command("/baselines", {
      code: draft.code,
      budget_version_id: Number(draft.budget_version_id),
      previous_baseline_id: draft.previous_baseline_id ? Number(draft.previous_baseline_id) : null,
      reason,
    });
    setSelectedId(String(result.id));
  }
  function select(row: CostRow) {
    setSelectedId(String(row.id));
  }
  return (
    <section className="costPanel">
      <h3>Cost Baseline</h3>
      <p>
        Baseline = Budget aprobado + control structure + mappings + phasing. Aprobar congela el snapshot y hash; Current
        Budget no reescribe el original.
      </p>
      <Records
        label="Cost Baselines"
        rows={data.baselines}
        columns={[
          ["code", "Código"],
          ["revision", "Revisión"],
          ["budget_version_id", "Budget aprobado"],
          ["status", "Estado"],
          ["content_hash", "Hash"],
          ["previous_baseline_id", "Baseline anterior"],
          ["approved_by", "Aprobador"],
        ]}
        select={select}
      />
      {can("baseline.prepare") ? (
        <form className="costForm" onSubmit={(event) => void save(event).catch(() => undefined)}>
          <Input
            label="Cost Baseline Code"
            required
            value={draft.code}
            onChange={(code) => setDraft({ ...draft, code })}
          />
          <Select
            label="Cost Baseline Budget"
            required
            rows={data.budgets.filter((row) => row.status === "APPROVED")}
            value={draft.budget_version_id}
            onChange={(budget_version_id) => setDraft({ ...draft, budget_version_id })}
          />
          <Select
            label="Cost Baseline Previous"
            rows={data.baselines.filter((row) => row.status === "APPROVED")}
            value={draft.previous_baseline_id}
            onChange={(previous_baseline_id) => setDraft({ ...draft, previous_baseline_id })}
          />
          <button disabled={busy || reason.trim().length < 8} type="submit">
            Crear Cost Baseline Candidate
          </button>
        </form>
      ) : null}
      {selected ? (
        <>
          <p>
            #{selected.id} · {text(selected, "status")}. Preparar la distribución en Cost Phasing antes de aprobar.
          </p>
          {selected.status === "CANDIDATE" && can("baseline.approve") ? (
            <button
              type="button"
              disabled={busy || reason.trim().length < 8}
              onClick={() =>
                void command(`/baselines/${selected.id}/approve`, { reason }, selected.version).catch(() => undefined)
              }
            >
              Aprobar Cost Baseline independiente
            </button>
          ) : null}
          <Evidence label="Cost Baseline snapshot inmutable" value={selected} />
        </>
      ) : null}
    </section>
  );
}
